import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, case, delete, exists, func, or_, select
from starlette.requests import ClientDisconnect

from rushes.api_common import DB, Access, owned, row_json
from rushes.auth import require_editor, stream_access
from rushes.config import settings
from rushes.db import tenant_session
from rushes.job_actions import cancel_batch_children, queue_asset
from rushes.models import (
    Asset,
    CollectionItem,
    Embedding,
    Export,
    Job,
    MediaTimeline,
    Observation,
    ObservationRevision,
    Project,
    Shot,
)
from rushes.storage import StorageError, open_source, require_space, sync_file
from rushes.timing import Interval

router = APIRouter(prefix="/api/workspaces/{workspace_id}")
EXTENSIONS = {".mp4", ".mov", ".mkv", ".mxf", ".avi", ".mts", ".m2ts", ".webm", ".m4v"}


class IndexInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root: int = Field(ge=0)
    paths: list[str] = Field(min_length=1, max_length=200)


def public_asset(asset: Asset, retry_available=False):
    row = row_json(asset)
    for key in ["source_root", "proxy_path", "thumbnail_path"]:
        row.pop(key)
    row["has_preview"] = bool(asset.proxy_path)
    row["can_retry"] = retry_available
    row["has_thumbnail"] = bool(asset.thumbnail_path)
    return row


@router.get("/source-roots")
async def source_roots(access: Access):
    require_editor(access)
    return [
        {"id": index, "name": root.name, "path": str(root)}
        for index, root in enumerate(settings().source_roots)
    ]


def root_at(index: int) -> Path:
    roots = settings().source_roots
    if not 0 <= index < len(roots):
        raise HTTPException(404, "Configured source root not found")
    return roots[index]


@router.get("/source-roots/{root_id}/files")
async def root_files(root_id: int, access: Access, limit: int = Query(200, ge=1, le=500)):
    require_editor(access)
    root = root_at(root_id)

    def scan():
        files = []
        inspected = 0
        for folder, directories, filenames in os.walk(root, followlinks=False):
            directories[:] = [
                name
                for name in sorted(directories)
                if not (Path(folder) / name).is_symlink() and not name.startswith(".")
            ]
            for filename in sorted(filenames):
                inspected += 1
                if inspected > 10000:
                    return {"files": files, "truncated": True}
                path = Path(folder) / filename
                if path.suffix.lower() in EXTENSIONS and not path.is_symlink():
                    files.append(str(path.relative_to(root)))
                    if len(files) >= limit:
                        return {"files": files, "truncated": True}
        return {"files": files, "truncated": False}

    return await asyncio.to_thread(scan)


@router.post("/projects/{project_id}/index", status_code=202)
async def index_sources(project_id: uuid.UUID, body: IndexInput, db: DB, access: Access):
    require_editor(access)
    await owned(db, Project, project_id, access)
    root = root_at(body.root)
    batch_id = uuid.uuid4()
    batch = Job(
        id=batch_id,
        workspace_id=access.workspace_id,
        project_id=project_id,
        kind="batch",
        workflow_id=f"batch:{batch_id}",
    )
    db.add(batch)
    results = []
    for relative in dict.fromkeys(body.paths):
        try:
            if Path(relative).suffix.lower() not in EXTENSIONS:
                raise StorageError("Unsupported video extension")
            with open_source(root, relative) as source:
                stat = os.fstat(source.fileno())
            existing = await db.scalar(
                select(Asset).where(
                    Asset.project_id == project_id,
                    Asset.source_root == str(root),
                    Asset.relative_path == relative,
                )
            )
            if existing:
                if (existing.source_size, existing.source_mtime_ns) != (
                    stat.st_size,
                    stat.st_mtime_ns,
                ):
                    raise StorageError(
                        "This indexed path changed. Upload it as a new file, or select a distinct indexed path; the previous asset still references its original fingerprint."
                    )
                results.append(
                    {"path": relative, "asset_id": existing.id, "state": "already_indexed"}
                )
                continue
            asset = Asset(
                workspace_id=access.workspace_id,
                project_id=project_id,
                name=Path(relative).name,
                source_root=str(root),
                relative_path=relative,
                import_relative_path=relative,
                source_size=stat.st_size,
                source_mtime_ns=stat.st_mtime_ns,
            )
            db.add(asset)
            await db.flush()
            queue_asset(db, asset, payload={"batch_id": str(batch_id)})
            results.append({"path": relative, "asset_id": asset.id, "state": "queued"})
        except StorageError as error:
            results.append({"path": relative, "state": "failed", "error": str(error)})
    return {"files": results, "batch_job_id": batch_id}


@router.post("/projects/{project_id}/upload", status_code=202)
async def upload(
    project_id: uuid.UUID,
    request: Request,
    access: Access,
    filename: str = Query(min_length=1, max_length=255),
    relative_path: str = Query(default="", max_length=2000),
):
    require_editor(access)
    async with tenant_session(access.workspace_id) as db:
        await owned(db, Project, project_id, access)
    config = settings()
    suffix = Path(filename).suffix.lower()
    if Path(filename).name != filename or suffix not in EXTENSIONS:
        raise HTTPException(422, "Choose a supported video file")
    relative = relative_path or filename
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise HTTPException(422, "Invalid relative import path")
    id = uuid.uuid4()
    folder = config.storage_root / "uploads" / str(access.workspace_id) / str(id)
    folder.mkdir(parents=True, mode=0o700)
    final = folder / f"original{suffix}"
    temporary = folder / "upload.part"
    count = 0
    try:
        length = int(request.headers.get("content-length", "0"))
        if length < 0 or length > config.max_upload_bytes:
            raise HTTPException(413, "File exceeds the configured upload size limit")
        require_space(folder, length, config.min_free_bytes)
        with temporary.open("xb") as file:
            async with asyncio.timeout(config.upload_timeout_seconds):
                async for chunk in request.stream():
                    count += len(chunk)
                    if count > config.max_upload_bytes:
                        raise HTTPException(413, "File exceeds the configured upload size limit")
                    require_space(folder, len(chunk), config.min_free_bytes)
                    await asyncio.to_thread(file.write, chunk)
            await asyncio.to_thread(sync_file, file)
        if not count or length and count != length:
            raise HTTPException(400, "Upload was incomplete. Please reselect this file.")
        os.replace(temporary, final)
        asset = Asset(
            id=id,
            workspace_id=access.workspace_id,
            project_id=project_id,
            name=filename,
            source_root=str(folder),
            relative_path=final.name,
            source_kind="uploaded",
            import_relative_path=relative,
            source_size=count,
            source_mtime_ns=final.stat().st_mtime_ns,
        )
        # Uploads can outlive a role change or logout. Recheck access before publishing work.
        access = await stream_access(request, access.workspace_id)
        require_editor(access)
        async with tenant_session(access.workspace_id) as db:
            await owned(db, Project, project_id, access)
            db.add(asset)
            await db.flush()
            queue_asset(db, asset)
        return {"asset_id": id, "state": "queued", "import_relative_path": relative}
    except Exception as error:
        final.unlink(missing_ok=True)
        if isinstance(error, TimeoutError):
            raise HTTPException(
                408,
                "Upload took too long. Reselect the file or ask the instance operator to increase the upload duration limit.",
            ) from error
        if isinstance(error, (StorageError, ClientDisconnect)):
            raise HTTPException(
                400, str(error) or "Upload disconnected; reselect the file"
            ) from error
        raise
    finally:
        temporary.unlink(missing_ok=True)


async def retry_capabilities(db, ids):
    rows = await db.execute(
        select(Job.asset_id, Job.state)
        .where(Job.asset_id.in_(ids), Job.kind == "asset")
        .distinct(Job.asset_id)
        .order_by(Job.asset_id, Job.created_at.desc(), Job.id.desc())
    )
    capabilities = {id: state in {"failed", "canceled"} for id, state in rows}
    failed_indexes = await db.scalars(
        select(Job.asset_id)
        .where(Job.asset_id.in_(ids), Job.kind == "index", Job.state.in_(["failed", "canceled"]))
        .distinct()
    )
    for id in failed_indexes:
        capabilities[id] = True
    return capabilities


@router.get("/projects/{project_id}/assets")
async def assets(
    project_id: uuid.UUID,
    db: DB,
    access: Access,
    offset: int = Query(0, ge=0),
    limit: int = Query(40, ge=1, le=100),
    uncategorized: bool = False,
):
    await owned(db, Project, project_id, access)
    filters = [Asset.project_id == project_id]
    if uncategorized:
        filters.append(~exists().where(CollectionItem.asset_id == Asset.id))
    rows = await db.scalars(
        select(Asset).where(*filters).order_by(Asset.created_at.desc()).offset(offset).limit(limit)
    )
    total = await db.scalar(select(func.count()).select_from(Asset).where(*filters))
    rows = list(rows)
    capabilities = await retry_capabilities(db, [row.id for row in rows])
    return {
        "items": [public_asset(asset, capabilities.get(asset.id, False)) for asset in rows],
        "total": total,
    }


@router.get("/assets/{asset_id}")
async def asset_detail(asset_id: uuid.UUID, db: DB, access: Access):
    asset = await owned(db, Asset, asset_id, access)
    timelines = list(
        await db.scalars(select(MediaTimeline).where(MediaTimeline.asset_id == asset_id))
    )
    shots = list(
        await db.scalars(
            select(Shot).where(Shot.asset_id == asset_id).order_by(Shot.start_us).limit(1000)
        )
    )
    capability = await retry_capabilities(db, [asset.id])
    return {
        **public_asset(asset, capability.get(asset.id, False)),
        "timelines": [
            {
                "id": t.id,
                "kind": t.kind,
                "details": {k: v for k, v in t.details.items() if k != "frame_map"},
            }
            for t in timelines
        ],
        "shots": [row_json(shot) for shot in shots],
    }


@router.get("/assets/{asset_id}/media/{kind}")
async def media(asset_id: uuid.UUID, kind: str, db: DB, access: Access):
    asset = await owned(db, Asset, asset_id, access)
    path = (
        asset.proxy_path
        if kind == "proxy"
        else asset.thumbnail_path
        if kind == "thumbnail"
        else None
    )
    if not path:
        raise HTTPException(404, "Preview is not ready")
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(settings().storage_root):
        raise HTTPException(404, "Preview unavailable")
    return FileResponse(resolved, media_type="video/mp4" if kind == "proxy" else "image/jpeg")


@router.get("/assets/{asset_id}/observations")
async def observations(
    asset_id: uuid.UUID,
    db: DB,
    access: Access,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    kind: Literal["all", "speech", "visual"] = "all",
    near_us: int | None = Query(None, ge=0),
):
    await owned(db, Asset, asset_id, access)
    filters = [Observation.asset_id == asset_id]
    if kind != "all":
        filters.append(
            Observation.kind == "speech" if kind == "speech" else Observation.kind != "speech"
        )
    if near_us is not None:
        anchor = await db.scalar(
            select(Observation)
            .where(*filters)
            .order_by(
                (and_(Observation.start_us <= near_us, Observation.end_us > near_us)).desc(),
                func.abs(Observation.start_us - near_us),
                Observation.id,
            )
            .limit(1)
        )
        if anchor:
            before = await db.scalar(
                select(func.count())
                .select_from(Observation)
                .where(
                    *filters,
                    or_(
                        Observation.start_us < anchor.start_us,
                        and_(Observation.start_us == anchor.start_us, Observation.id < anchor.id),
                    ),
                )
            )
            offset = (before // limit) * limit
    count = await db.scalar(select(func.count()).select_from(Observation).where(*filters))
    offset = min(offset, max(0, ((count - 1) // limit) * limit))
    rows = await db.scalars(
        select(Observation)
        .where(*filters)
        .order_by(Observation.start_us, Observation.id)
        .offset(offset)
        .limit(limit)
    )
    return {"items": [row_json(row) for row in rows], "total": count, "offset": offset}


class Correction(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    description: str = Field(min_length=1, max_length=4000)
    start_us: int = Field(ge=0)
    end_us: int = Field(gt=0)
    version: int = Field(ge=1)


@router.patch("/observations/{observation_id}")
async def correct(observation_id: uuid.UUID, body: Correction, db: DB, access: Access):
    require_editor(access)
    observation = await db.scalar(
        select(Observation)
        .where(Observation.id == observation_id, Observation.workspace_id == access.workspace_id)
        .with_for_update()
    )
    if observation is None:
        raise HTTPException(404, "Observation not found")
    if observation.version != body.version:
        raise HTTPException(409, "This observation changed. Reload it before saving.")
    asset = await owned(db, Asset, observation.asset_id, access)
    try:
        Interval(start_us=body.start_us, end_us=body.end_us).within(asset.duration_us)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    before = {
        "description": observation.description,
        "start_us": observation.start_us,
        "end_us": observation.end_us,
    }
    after = body.model_dump(exclude={"version"})
    if before == after:
        return row_json(observation)
    db.add(
        ObservationRevision(
            workspace_id=access.workspace_id,
            observation_id=observation.id,
            user_id=access.user_id,
            version=observation.version,
            before=before,
            after=after,
        )
    )
    for key, value in after.items():
        setattr(observation, key, value)
    observation.version += 1
    observation.review_status = "corrected"
    if before["description"] != observation.description:
        await db.execute(delete(Embedding).where(Embedding.observation_id == observation.id))
        queue_asset(db, asset, kind="index", payload={"observation_ids": [str(observation.id)]})
    return row_json(observation)


@router.get("/observations/{observation_id}/history")
async def history(observation_id: uuid.UUID, db: DB, access: Access):
    await owned(db, Observation, observation_id, access)
    return [
        row_json(row)
        for row in await db.scalars(
            select(ObservationRevision)
            .where(ObservationRevision.observation_id == observation_id)
            .order_by(ObservationRevision.version.desc())
            .limit(100)
        )
    ]


def recent_jobs(query):
    return query.order_by(
        case(
            (Job.state.in_(["running", "cancel_requested"]), 0),
            (Job.state == "dispatched", 1),
            (Job.state == "queued", 2),
            else_=3,
        ),
        Job.updated_at.desc(),
        Job.id,
    ).limit(100)


@router.get("/jobs")
async def jobs(db: DB, access: Access, project_id: uuid.UUID | None = None):
    query = select(Job).where(Job.workspace_id == access.workspace_id)
    if project_id:
        await owned(db, Project, project_id, access)
        query = query.where(Job.project_id == project_id)
    return [row_json(job) for job in await db.scalars(recent_jobs(query))]


@router.get("/events")
async def events(request: Request, workspace_id: uuid.UUID, project_id: uuid.UUID | None = None):
    access = await stream_access(request, workspace_id)
    if project_id:
        async with tenant_session(access.workspace_id) as db:
            await owned(db, Project, project_id, access)

    async def stream():
        previous = None
        while not await request.is_disconnected():
            try:
                await stream_access(request, workspace_id)
            except HTTPException:
                yield 'event: session-expired\ndata: {"message":"Session or membership ended"}\n\n'
                return
            async with tenant_session(access.workspace_id) as db:
                query = select(Job).where(Job.workspace_id == access.workspace_id)
                if project_id:
                    query = query.where(Job.project_id == project_id)
                jobs = list(await db.scalars(recent_jobs(query)))
                snapshot = json.dumps([row_json(job) for job in jobs], default=str)
            if snapshot != previous:
                yield f"data: {snapshot}\n\n"
                previous = snapshot
            else:
                yield ": keepalive\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
    )


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: uuid.UUID, db: DB, access: Access):
    require_editor(access)
    job = await db.scalar(select(Job).where(Job.id == job_id).with_for_update())
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.state == "queued":
        job.state, job.stage = "canceled", "Canceled before processing"
        if job.kind == "batch":
            await cancel_batch_children(db, job.id)
        if job.asset_id and job.kind == "asset":
            asset = await db.get(Asset, job.asset_id)
            asset.status, asset.error = "canceled", "Canceled before processing"
        if job.kind == "export":
            output = await db.scalar(select(Export).where(Export.job_id == job.id))
            output.state = "canceled"
    elif job.state in {"dispatched", "running"}:
        job.state, job.stage = "cancel_requested", "Cancellation requested; waiting for worker"
    return {"state": job.state}


@router.post("/assets/{asset_id}/retry", status_code=202)
async def retry_asset(asset_id: uuid.UUID, db: DB, access: Access):
    require_editor(access)
    asset = await db.scalar(select(Asset).where(Asset.id == asset_id).with_for_update())
    if asset is None:
        raise HTTPException(404, "Asset not found")
    active = await db.scalar(
        select(Job.id)
        .where(
            Job.asset_id == asset_id,
            Job.kind.in_(["asset", "index"]),
            Job.state.in_(["queued", "dispatched", "running", "cancel_requested"]),
        )
        .limit(1)
    )
    if active:
        raise HTTPException(409, "This asset already has an active job")
    latest_asset_job = (
        select(Job.id)
        .where(Job.asset_id == asset_id, Job.kind == "asset")
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(1)
    )
    job = await db.scalar(
        select(Job)
        .where(
            Job.asset_id == asset_id,
            (Job.id.in_(latest_asset_job)) | (Job.kind == "index"),
            Job.state.in_(["failed", "canceled"]),
        )
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(1)
    )
    if job is None or job.state not in {"failed", "canceled"}:
        raise HTTPException(
            409,
            "Only failed or canceled processing can be retried. Review an analysis estimate for new analysis.",
        )
    # A retry changes execution identity, never the billing operation or analysis run.
    job.workflow_id = f"{job.kind}:{asset.id}:{job.id}:retry:{uuid.uuid4()}"
    job.payload = {
        **{key: value for key, value in job.payload.items() if key != "batch_id"},
        "recovery_attempt": job.payload.get("recovery_attempt", 0) + 1,
    }
    job.state, job.error, job.stage = "queued", None, "Waiting to resume verified checkpoints"
    if job.kind == "asset":
        asset.status, asset.error = "queued", None
    return {"job_id": job.id, "state": "queued"}


class NoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    description: str = Field(min_length=1, max_length=4000)
    start_us: int = Field(ge=0)
    end_us: int = Field(gt=0)
    request_id: uuid.UUID


@router.post("/assets/{asset_id}/observations", status_code=201)
async def add_note(asset_id: uuid.UUID, body: NoteInput, db: DB, access: Access):
    require_editor(access)
    asset = await owned(db, Asset, asset_id, access)
    try:
        Interval(start_us=body.start_us, end_us=body.end_us).within(asset.duration_us or 0)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    timeline = await db.scalar(
        select(MediaTimeline).where(
            MediaTimeline.asset_id == asset_id, MediaTimeline.kind == "source"
        )
    )
    if timeline is None:
        raise HTTPException(409, "Wait for source inspection before adding notes")
    operation = f"note:{access.workspace_id}:{asset_id}:{body.request_id}"
    existing = await db.scalar(select(Observation).where(Observation.operation_key == operation))
    if existing:
        return row_json(existing)
    note = Observation(
        workspace_id=access.workspace_id,
        asset_id=asset_id,
        timeline_id=timeline.id,
        operation_key=operation,
        kind="note",
        description=body.description,
        start_us=body.start_us,
        end_us=body.end_us,
        proposed_start_us=body.start_us,
        proposed_end_us=body.end_us,
        producer="user",
        model="none",
        prompt_version="manual-v1",
        preprocessing_version="source",
        review_status="reviewed",
        uncertainty="user-selected interval",
        evidence=[{"user_id": str(access.user_id)}],
    )
    db.add(note)
    await db.flush()
    queue_asset(db, asset, kind="index", payload={"observation_ids": [str(note.id)]})
    return row_json(note)
