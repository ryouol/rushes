"""Bounded cleanup of expired local units and recorded remote provider files."""

import asyncio
import logging
import re
import time
from datetime import timedelta

from sqlalchemy import select

from rushes.config import settings
from rushes.db import session_factory, tenant_session
from rushes.models import AnalysisWindow, Workspace, now
from rushes.provider_files import delete_provider_file

logger = logging.getLogger("rushes.maintenance")


def delete_remote(name):
    from google import genai
    from google.genai import types

    config = settings()
    with genai.Client(
        api_key=config.gemini_api_key.get_secret_value(),
        http_options=types.HttpOptions(
            timeout=30_000, retry_options=types.HttpRetryOptions(attempts=1)
        ),
    ) as client:
        delete_provider_file(client, name)


def unit_paths():
    for root in (settings().storage_root, settings().output_root):
        yield from root.rglob("*")


def clean_old_units(paths):
    cutoff = time.time() - 86400
    for _ in range(10000):
        try:
            path = next(paths)
        except StopIteration:
            return unit_paths()
        try:
            if (
                path.is_file()
                and (
                    path.name.endswith((".partial", ".partial.json"))
                    or re.search(r"^\..*\.[0-9a-f]{32}\.partial\.(mp4|gz)$", path.name)
                    or path.name == "upload.part"
                    or path.name.startswith(("audio-", "chunk-"))
                )
                and path.stat().st_mtime < cutoff
            ):
                path.unlink()
        except FileNotFoundError:
            pass
    return paths


async def cleanup_provider_files(workspace_id):
    async with tenant_session(workspace_id) as db:
        rows = list(
            await db.execute(
                select(AnalysisWindow.id, AnalysisWindow.provider_file)
                .where(
                    AnalysisWindow.provider_file.is_not(None),
                    AnalysisWindow.state.in_(["received", "completed", "ambiguous", "failed"]),
                    AnalysisWindow.created_at < now() - timedelta(hours=1),
                )
                .order_by(AnalysisWindow.created_at, AnalysisWindow.id)
                .limit(20)
            )
        )
    for row in rows:
        try:
            await asyncio.to_thread(delete_remote, row.provider_file)
            async with tenant_session(workspace_id) as db:
                current = await db.get(AnalysisWindow, row.id, with_for_update=True)
                if current and current.provider_file == row.provider_file:
                    current.provider_file = None
        except Exception:
            logger.warning("Provider file cleanup will retry", exc_info=True)


async def maintain():
    paths = unit_paths()
    while True:
        try:
            paths = await asyncio.to_thread(clean_old_units, paths)
            config = settings()
            if config.gemini_api_key and config.gemini_api_key.get_secret_value():
                async with session_factory()() as db:
                    ids = list(await db.scalars(select(Workspace.id)))
                for workspace_id in ids:
                    await cleanup_provider_files(workspace_id)
        except Exception:
            logger.warning(
                "Artifact cleanup will retry on the next maintenance pass", exc_info=True
            )
        await asyncio.sleep(60)
