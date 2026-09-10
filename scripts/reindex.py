"""Build a model-specific vector index and queue durable re-embedding for existing worklogs."""

import asyncio
import hashlib

from rushes.config import settings
from rushes.db import session_factory, tenant_session
from rushes.inference import embedder
from rushes.job_actions import queue_asset
from rushes.models import Asset, Job, Observation, Workspace
from sqlalchemy import literal, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import create_async_engine


async def main():
    config = settings()
    admin_url = config.require_admin_database_url()
    dimension = len(
        await asyncio.to_thread(lambda: embedder().embed(["Dimension verification"])[0])
    )
    if not 1 <= dimension <= 2000:
        raise SystemExit(
            "This model exceeds the HNSW vector dimension limit; select an index strategy before switching."
        )
    model_sql = str(
        literal(config.embedding_model).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    identity = hashlib.sha256(config.embedding_model.encode()).hexdigest()[:16]
    admin = create_async_engine(
        admin_url.get_secret_value(),
        isolation_level="AUTOCOMMIT",
        hide_parameters=True,
    )
    try:
        async with admin.connect() as connection:
            await connection.execute(
                text(
                    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS embedding_{identity}_{dimension} ON embedding USING hnsw ((vector::vector({dimension})) vector_cosine_ops) WHERE model={model_sql} AND dimension={dimension}"
                )
            )
    finally:
        await admin.dispose()
    count = 0
    async with session_factory()() as db:
        ids = list(await db.scalars(select(Workspace.id)))
    for workspace_id in ids:
        async with tenant_session(workspace_id) as db:
            assets = await db.stream_scalars(
                select(Asset)
                .where(Asset.id.in_(select(Observation.asset_id)))
                .execution_options(yield_per=100)
            )
            async for asset in assets:
                active = await db.scalar(
                    select(Job.id)
                    .where(
                        Job.asset_id == asset.id,
                        Job.kind == "index",
                        Job.state.in_(["queued", "dispatched", "running"]),
                    )
                    .limit(1)
                )
                if not active:
                    queue_asset(db, asset, kind="index")
                    count += 1
    print(
        f"Verified dimension {dimension}; model index prepared; {count} durable reindex jobs queued. No provider credits used."
    )


if __name__ == "__main__":
    asyncio.run(main())
