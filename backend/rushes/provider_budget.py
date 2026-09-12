"""Reserve conservative provider exposure before any paid dispatch."""

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

import psycopg
from sqlalchemy.engine import make_url

from rushes.config import settings

# USD micro-units. Reservations remain consumed even after ambiguous or failed calls.
# Pro: 10k input at $2/M plus 4096 output/thinking at $12/M, rounded up.
# Reviewed against Google's standard pricing on 2026-09-12; also covers retained Flash runs.
CALL_ALLOWANCE = {"gemini": 75_000, "modal": 10_000}


class ProviderBudgetError(ValueError):
    pass


def current_month():
    return datetime.now(UTC).date().replace(day=1)


def reserve_provider_call(provider: Literal["gemini", "modal"]):
    config = settings()
    limit = config.provider_monthly_allowance_microusd
    if limit is None:
        return
    amount = CALL_ALLOWANCE[provider]
    period = current_month()
    url = make_url(config.database_url.get_secret_value())
    try:
        with psycopg.connect(
            url.set(drivername="postgresql", query={}).render_as_string(hide_password=False),
            **{**url.query, "connect_timeout": 5},
        ) as db:
            db.execute("SET LOCAL lock_timeout = '5s'")
            db.execute("SET LOCAL statement_timeout = '5s'")
            db.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"rushes-provider-budget:{period}",),
            )
            used = db.execute(
                "SELECT COALESCE(sum(amount_microusd), 0) FROM provider_spend_reservation WHERE month=%s",
                (period,),
            ).fetchone()[0]
            if used + amount > limit:
                raise ProviderBudgetError(
                    "The monthly AI allowance is used up. Existing footage remains available; new AI requests resume next month."
                )
            db.execute(
                "INSERT INTO provider_spend_reservation (id, month, provider, amount_microusd) VALUES (%s,%s,%s,%s)",
                (uuid4(), period, provider, amount),
            )
    except psycopg.Error as error:
        raise ProviderBudgetError(
            "AI spending checks are unavailable. No provider request was sent."
        ) from error
