"""Persist the deployment's conservative monthly provider reservations."""

from alembic import op

revision = "0005"
down_revision = "0004"


def upgrade():
    op.execute("""
        CREATE TABLE provider_spend_reservation (
            id UUID PRIMARY KEY,
            month DATE NOT NULL,
            provider VARCHAR(16) NOT NULL CHECK (provider IN ('gemini','modal')),
            amount_microusd BIGINT NOT NULL CHECK (amount_microusd > 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX provider_spend_reservation_month ON provider_spend_reservation (month);
        GRANT SELECT, INSERT ON provider_spend_reservation TO rushes_app;
    """)


def downgrade():
    raise RuntimeError("Removing spending history requires an explicit retention decision")
