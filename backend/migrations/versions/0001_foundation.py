"""Initial normalized local schema, pgvector and forced tenant RLS."""

from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None


def upgrade():
    schema = Path(__file__).with_name("0001_schema.sql").read_text()
    for statement in schema.split(";\n"):
        if statement.strip():
            op.execute(statement)


def downgrade():
    raise RuntimeError(
        "Initial schema downgrade would destroy footage records. Restore a database backup instead."
    )
