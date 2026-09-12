"""Settle provider holds without rewriting spending history."""

from alembic import op

revision = "0008"
down_revision = "0007"


def upgrade():
    op.execute("""
        CREATE TABLE provider_spend_settlement (
            reservation_id UUID PRIMARY KEY REFERENCES provider_spend_reservation(id),
            amount_microusd BIGINT NOT NULL CHECK (amount_microusd >= 0),
            evidence JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        GRANT SELECT, INSERT ON provider_spend_settlement TO rushes_app;
    """)


def downgrade():
    raise RuntimeError("Removing spending history requires an explicit retention decision")
