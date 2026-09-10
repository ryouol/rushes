from contextlib import asynccontextmanager
from functools import lru_cache
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from rushes.config import settings


@lru_cache
def session_factory():
    engine = create_async_engine(
        settings().database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        hide_parameters=True,
    )
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session():
    async with session_factory()() as session:
        yield session


@asynccontextmanager
async def tenant_session(workspace_id: UUID | str):
    """Used only after API membership authorization, or by trusted ID-only activities."""
    async with session_factory()() as session, session.begin():
        await session.execute(
            text("SELECT set_config('rushes.workspace_id', :workspace, true)"),
            {"workspace": str(UUID(str(workspace_id)))},
        )
        yield session
