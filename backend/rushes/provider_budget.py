"""Hold maximum exposure, then settle only provider-confirmed outcomes."""

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb
from sqlalchemy.engine import make_url

from rushes.config import settings

# USD micro-units. Unknown outcomes retain the full hold.
# Pro: 10k input at $2/M plus 4096 output/thinking at $12/M, rounded up.
# Reviewed against Google's standard pricing on 2026-09-12; also covers retained Flash runs.
CALL_ALLOWANCE = {"gemini": 75_000, "modal": 10_000}


class ProviderBudgetError(ValueError):
    pass


def current_month():
    return datetime.now(UTC).date().replace(day=1)


@contextmanager
def budget_connection():
    url = make_url(settings().database_url.get_secret_value())
    try:
        with psycopg.connect(
            url.set(drivername="postgresql", query={}).render_as_string(hide_password=False),
            **{**url.query, "connect_timeout": 5},
        ) as db:
            db.execute("SET LOCAL lock_timeout = '5s'")
            db.execute("SET LOCAL statement_timeout = '5s'")
            yield db
    except psycopg.Error as error:
        raise ProviderBudgetError(
            "AI spending checks are unavailable. No new provider request was sent."
        ) from error


def lock_month(db, period):
    db.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"rushes-provider-budget:{period}",),
    )


def reserve_provider_call(provider: Literal["gemini", "modal"]) -> UUID | None:
    limit = settings().provider_monthly_allowance_microusd
    if limit is None:
        return None
    amount = CALL_ALLOWANCE[provider]
    period, reservation_id = current_month(), uuid4()
    with budget_connection() as db:
        lock_month(db, period)
        used = db.execute(
            """SELECT COALESCE(sum(COALESCE(s.amount_microusd, r.amount_microusd)), 0)
               FROM provider_spend_reservation r
               LEFT JOIN provider_spend_settlement s ON s.reservation_id=r.id
               WHERE r.month=%s""",
            (period,),
        ).fetchone()[0]
        if used + amount > limit:
            raise ProviderBudgetError(
                "Processing is paused at this month's AI spending limit. "
                "Completed analysis is saved. Resume processing when allowance is available; "
                "the monthly allowance renews on the 1st."
            )
        db.execute(
            "INSERT INTO provider_spend_reservation (id, month, provider, amount_microusd) VALUES (%s,%s,%s,%s)",
            (reservation_id, period, provider, amount),
        )
    return reservation_id


def gemini_cost_microusd(model: str, usage: dict, period) -> int | None:
    """Standard text-output pricing; missing usage never releases a hold."""
    prompt, total = usage.get("prompt_token_count"), usage.get("total_token_count")
    candidates, thoughts = (
        usage.get("candidates_token_count") or 0,
        usage.get("thoughts_token_count") or 0,
    )
    if any(type(n) is not int or n < 0 for n in (prompt, total, candidates, thoughts)):
        return None
    if total < prompt:
        return None
    output = max(total - prompt, candidates + thoughts)
    # Nano-USD/token, rounded up once to micro-USD. Cached inputs are conservatively
    # charged at full price. No tools, grounding, caching storage or media output are enabled.
    if model == "gemini-3.1-pro-preview":
        input_rate, output_rate = (2000, 12000) if prompt <= 200_000 else (4000, 18000)
    elif model == "gemini-3.6-flash":
        input_rate, output_rate = (750, 3750) if period.year < 2027 else (1500, 7500)
    else:
        return None
    return (prompt * input_rate + output * output_rate + 999) // 1000


def settle_gemini_call(
    reservation_id: UUID | None,
    *,
    model: str,
    usage: dict | None = None,
    rejected=False,
    rejection_evidence: dict | None = None,
):
    if reservation_id is None:
        return
    if not rejected and gemini_cost_microusd(model, usage or {}, current_month()) is None:
        return
    with budget_connection() as db:
        reservation = db.execute(
            "SELECT month, provider FROM provider_spend_reservation WHERE id=%s",
            (reservation_id,),
        ).fetchone()
        if reservation is None or reservation[1] != "gemini":
            raise ValueError("Gemini settlement requires an existing Gemini reservation")
        period = reservation[0]
        amount = 0 if rejected else gemini_cost_microusd(model, usage or {}, period)
        if amount is None:
            return
        lock_month(db, period)
        evidence = {
            "model": model,
            "usage": usage,
            "outcome": "not_generated" if rejected else "received",
            "pricing": "google-standard-2026-09-12",
        }
        if rejected:
            evidence["rejection"] = rejection_evidence
        db.execute(
            """INSERT INTO provider_spend_settlement (reservation_id, amount_microusd, evidence)
               VALUES (%s,%s,%s) ON CONFLICT (reservation_id) DO NOTHING""",
            (reservation_id, amount, Jsonb(evidence)),
        )
        existing = db.execute(
            "SELECT amount_microusd, evidence FROM provider_spend_settlement WHERE reservation_id=%s",
            (reservation_id,),
        ).fetchone()
        if existing != (amount, evidence):
            raise ValueError("Provider settlement conflicts with its recorded outcome")
