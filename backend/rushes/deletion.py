"""Tenant-scoped deletion of records and strictly app-owned storage trees."""

import asyncio
import logging
import os
import shutil
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError

from rushes.auth import WorkspaceAccess, require_editor
from rushes.config import settings
from rushes.db import WorkspaceBusyError, tenant_session
from rushes.models import (
    AnalysisRun,
    AnalysisWindow,
    Asset,
    Collection,
    CollectionItem,
    Embedding,
    Export,
    Job,
    LedgerEntry,
    MediaTimeline,
    Membership,
    Observation,
    ObservationRevision,
    ProcessingEvent,
    Project,
    Reservation,
    Shot,
    Usage,
    Workspace,
)
from rushes.storage import run_storage_thread, workspace_file_lease

DeleteKind = Literal["workspace", "project", "asset", "export"]
FINISHED_JOBS = {"ready", "partial", "completed", "failed", "canceled", "draft"}
FINISHED_EXPORTS = {"completed", "failed", "canceled", "draft"}
logger = logging.getLogger("rushes.deletion")


@contextmanager
def owned_directory(root: Path, parts: tuple[str, ...]):
    """Return an anchored parent FD and final name; never follow a storage symlink."""
    handles = []
    try:
        try:
            parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            handles.append(parent)
            for part in parts[:-1]:
                parent = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                handles.append(parent)
            target = os.open(parts[-1], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            handles.append(target)
        except FileNotFoundError:
            yield None
            return
        yield parent, parts[-1], target
    finally:
        for fd in reversed(handles):
            os.close(fd)


def inspect_tree(directory_fd: int) -> tuple[int, int]:
    """Count owned regular files, and preflight writable directories without following links."""
    if not os.access(".", os.W_OK | os.X_OK, dir_fd=directory_fd):
        raise PermissionError("Storage directory is not writable")
    total, files = 0, 0
    for name in os.listdir(directory_fd):
        info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
            try:
                size, count = inspect_tree(child)
                total += size
                files += count
            finally:
                os.close(child)
        elif stat.S_ISREG(info.st_mode):
            # Removing one hardlink does not reclaim the linked file's bytes.
            total += info.st_size if info.st_nlink == 1 else 0
            files += 1
        elif not stat.S_ISLNK(info.st_mode):
            raise OSError("Unsupported file type in application storage")
    return total, files


def inspect_directories(directories):
    if not shutil.rmtree.avoids_symlink_attacks:
        raise OSError("This platform cannot safely remove directory trees")
    for root, parts in directories:
        with owned_directory(root, parts) as opened:
            if opened:
                parent, _, target = opened
                if not os.access(".", os.W_OK | os.X_OK, dir_fd=parent):
                    raise PermissionError("Storage parent is not writable")
                inspect_tree(target)


def remove_directories(directories):
    reclaimed, files = 0, 0
    for root, parts in directories:
        with owned_directory(root, parts) as opened:
            if opened:
                parent, name, target = opened
                size, count = inspect_tree(target)
                shutil.rmtree(name, dir_fd=parent)
                reclaimed += size
                files += count
    return {"deleted": True, "reclaimed_bytes": reclaimed, "deleted_files": files}


async def delete_records(db, workspace_id, kind, project_ids, asset_ids, exports, jobs):
    """Explicit FK order keeps tenant accounting until the workspace itself is removed."""
    job_ids, export_ids = [row.id for row in jobs], [row.id for row in exports]
    observations = select(Observation.id).where(
        Observation.workspace_id == workspace_id, Observation.asset_id.in_(asset_ids)
    )
    collections = select(Collection.id).where(
        Collection.workspace_id == workspace_id, Collection.project_id.in_(project_ids)
    )

    async def remove(model, condition):
        await db.execute(delete(model).where(model.workspace_id == workspace_id, condition))

    await remove(ObservationRevision, ObservationRevision.observation_id.in_(observations))
    await remove(Embedding, Embedding.observation_id.in_(observations))
    await remove(Observation, Observation.asset_id.in_(asset_ids))
    await remove(AnalysisWindow, AnalysisWindow.asset_id.in_(asset_ids))
    await remove(AnalysisRun, AnalysisRun.asset_id.in_(asset_ids))
    await remove(Shot, Shot.asset_id.in_(asset_ids))
    await remove(MediaTimeline, MediaTimeline.asset_id.in_(asset_ids))
    await remove(
        CollectionItem,
        or_(CollectionItem.asset_id.in_(asset_ids), CollectionItem.collection_id.in_(collections)),
    )
    await remove(Collection, Collection.id.in_(collections))
    await remove(Export, Export.id.in_(export_ids))
    await remove(ProcessingEvent, ProcessingEvent.job_id.in_(job_ids))
    await remove(Job, Job.id.in_(job_ids))
    await db.execute(
        update(Usage)
        .where(Usage.workspace_id == workspace_id, Usage.asset_id.in_(asset_ids))
        .values(asset_id=None)
    )
    await db.execute(
        update(Asset)
        .where(Asset.workspace_id == workspace_id, Asset.duplicate_of_id.in_(asset_ids))
        .values(duplicate_of_id=None)
    )
    await remove(Asset, Asset.id.in_(asset_ids))
    await remove(Project, Project.id.in_(project_ids))
    if kind == "workspace":
        await remove(Usage, Usage.workspace_id == workspace_id)
        await remove(LedgerEntry, LedgerEntry.workspace_id == workspace_id)
        await remove(Reservation, Reservation.workspace_id == workspace_id)
        await remove(Membership, Membership.workspace_id == workspace_id)
        await db.execute(delete(Workspace).where(Workspace.id == workspace_id))
    await db.flush()


async def _delete(access: WorkspaceAccess, kind: DeleteKind, record_id: UUID):
    workspace_id = access.workspace_id
    with workspace_file_lease(workspace_id, exclusive=True):
        async with tenant_session(workspace_id, exclusive=True) as db:
            member = await db.scalar(
                select(Membership).where(
                    Membership.workspace_id == workspace_id, Membership.user_id == access.user_id
                )
            )
            if member is None:
                raise HTTPException(404, "Workspace not found")
            current = WorkspaceAccess(workspace_id, access.user_id, member.role)
            workspace = await db.scalar(
                select(Workspace).where(Workspace.id == workspace_id).with_for_update()
            )
            if kind == "workspace":
                if current.role != "owner" or workspace.owner_id != current.user_id:
                    raise HTTPException(403, "Only the workspace owner can delete this workspace")
            else:
                require_editor(current)
                model = {"project": Project, "asset": Asset, "export": Export}[kind]
                columns = (Asset.id, Asset.project_id) if kind == "asset" else (model.id,)
                record = (
                    await db.execute(
                        select(*columns)
                        .where(model.workspace_id == workspace_id, model.id == record_id)
                        .with_for_update()
                    )
                ).one_or_none()
                if record is None:
                    raise HTTPException(404, "Record not found")
            project_ids = list(
                await db.scalars(
                    select(Project.id).where(
                        Project.workspace_id == workspace_id,
                        True
                        if kind == "workspace"
                        else Project.id == record_id
                        if kind == "project"
                        else False,
                    )
                )
            )
            asset_ids = list(
                await db.scalars(
                    select(Asset.id).where(
                        Asset.workspace_id == workspace_id,
                        Asset.id == record_id
                        if kind == "asset"
                        else Asset.project_id.in_(project_ids),
                    )
                )
            )
            exports = list(
                await db.execute(
                    select(Export.id, Export.job_id, Export.state)
                    .where(
                        Export.workspace_id == workspace_id,
                        Export.id == record_id
                        if kind == "export"
                        else Export.project_id.in_(project_ids),
                    )
                    .with_for_update()
                )
            )
            jobs = list(
                await db.execute(
                    select(Job.id, Job.state)
                    .where(
                        Job.workspace_id == workspace_id,
                        or_(
                            Job.project_id.in_(project_ids),
                            Job.asset_id.in_(asset_ids),
                            Job.id.in_([row.job_id for row in exports]),
                        ),
                    )
                    .with_for_update()
                )
            )
            if any(row.state not in FINISHED_JOBS for row in jobs) or any(
                row.state not in FINISHED_EXPORTS for row in exports
            ):
                raise HTTPException(
                    409,
                    "Processing or export work is active. Cancel it and wait for cancellation to finish, then delete.",
                )
            if asset_ids and await db.scalar(
                select(Asset.id)
                .where(
                    Asset.workspace_id == workspace_id,
                    Asset.id.in_(asset_ids),
                    Asset.status.in_(["queued", "processing", "preview_ready"]),
                )
                .limit(1)
            ):
                raise HTTPException(
                    409,
                    "Footage is still processing. Cancel its job and wait for it to finish, then delete.",
                )
            if kind == "asset" and await db.scalar(
                select(Export.id)
                .where(
                    Export.workspace_id == workspace_id,
                    Export.project_id == record.project_id,
                    Export.state != "completed",
                    or_(
                        Export.plan["entries"].contains([{"asset_id": str(record_id)}]),
                        Export.state.not_in(FINISHED_EXPORTS),
                    ),
                )
                .limit(1)
            ):
                raise HTTPException(
                    409,
                    "An unfinished export uses this footage. Cancel active exports and delete its export preview or failed export first.",
                )
            if kind == "asset" and await db.scalar(
                select(Job.id)
                .where(
                    Job.workspace_id == workspace_id,
                    Job.project_id == record.project_id,
                    Job.kind == "export",
                    Job.state.not_in(FINISHED_JOBS),
                )
                .limit(1)
            ):
                raise HTTPException(
                    409,
                    "An export is active in this project. Cancel it and wait for it to finish before deleting footage.",
                )
            if asset_ids and await db.scalar(
                select(AnalysisWindow.id)
                .where(
                    AnalysisWindow.workspace_id == workspace_id,
                    AnalysisWindow.asset_id.in_(asset_ids),
                    or_(
                        AnalysisWindow.provider_file.is_not(None),
                        AnalysisWindow.state == "in_flight",
                    ),
                )
                .limit(1)
            ):
                raise HTTPException(
                    409,
                    "AI cleanup is still finishing. Try again shortly; if it persists, ask your workspace administrator to check processing.",
                )
            reservation_filter = (
                True
                if kind == "workspace"
                else Reservation.operation_key.in_([f"analysis:{row.id}" for row in jobs])
            )
            if await db.scalar(
                select(Reservation.id)
                .where(
                    Reservation.workspace_id == workspace_id,
                    Reservation.state == "reserved",
                    reservation_filter,
                )
                .limit(1)
            ):
                raise HTTPException(
                    409,
                    "AI processing is still finishing. Wait for it to finish or cancel it, then retry deletion.",
                )
            config, ws = settings(), str(workspace_id)
            if kind == "workspace":
                directories = [
                    (config.storage_root, (ws,)),
                    (config.storage_root, ("uploads", ws)),
                    (config.output_root, (ws,)),
                ]
            else:
                directories = [
                    item
                    for asset_id in asset_ids
                    for item in (
                        (config.storage_root, (ws, str(asset_id))),
                        (config.storage_root, ("uploads", ws, str(asset_id))),
                    )
                ] + [(config.output_root, (ws, str(row.id))) for row in exports]
            # Validate every path and all database constraints before removing any bytes.
            await run_storage_thread(inspect_directories, directories)
            await delete_records(db, workspace_id, kind, project_ids, asset_ids, exports, jobs)
            result = await run_storage_thread(remove_directories, directories)
        # tenant_session commits before a success response; a failed cleanup rolls records back.
        return result


async def delete_resource(access: WorkspaceAccess, kind: DeleteKind, record_id: UUID):
    task = asyncio.create_task(_delete(access, kind, record_id))
    try:
        # A disconnected request must not release DB/file leases while cleanup is still running.
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
        task.result()
        raise
    except WorkspaceBusyError as error:
        raise HTTPException(409, str(error)) from error
    except IntegrityError as error:
        logger.warning(
            "Deletion blocked by record integrity: %s %s", kind, record_id, exc_info=True
        )
        raise HTTPException(
            409,
            "Related records prevent this deletion. Refresh and retry; if it persists, ask the instance operator to check record integrity.",
        ) from error
    except OSError as error:
        logger.warning("Deletion storage cleanup failed: %s %s", kind, record_id, exc_info=True)
        raise HTTPException(
            409,
            "Deletion could not finish. The item is still listed, but some files may already be removed. Ask your workspace administrator to check storage, then retry deletion.",
        ) from error
