"""Retain provider expiry and schedule unresolved cleanup fairly."""

from alembic import op

revision = "0007"
down_revision = "0006"


def upgrade():
    op.execute(
        "ALTER TABLE analysis_window "
        "ADD COLUMN provider_file_expires_at TIMESTAMPTZ, "
        "ADD COLUMN provider_file_retry_at TIMESTAMPTZ"
    )


def downgrade():
    raise RuntimeError("Removing provider retention evidence requires an explicit decision")
