"""Persist immutable per-window model inputs before dispatch."""

from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade():
    op.execute("ALTER TABLE analysis_window ADD COLUMN input_snapshot JSONB")


def downgrade():
    raise RuntimeError("Removing model provenance requires an explicit retention decision")
