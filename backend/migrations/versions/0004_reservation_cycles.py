"""Account for resumed analysis without charging completed coverage twice."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "reservation", sa.Column("cycle", sa.Integer(), nullable=False, server_default="0")
    )


def downgrade():
    op.drop_column("reservation", "cycle")
