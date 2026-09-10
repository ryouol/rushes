from alembic import context
from rushes.config import settings
from rushes.models import Base
from sqlalchemy import create_engine, pool

engine = create_engine(
    settings().require_admin_database_url().get_secret_value(),
    poolclass=pool.NullPool,
    hide_parameters=True,
)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
