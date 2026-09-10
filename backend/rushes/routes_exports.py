import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from rushes.api_common import DB, Access, owned
from rushes.auth import require_editor
from rushes.config import settings
from rushes.exports import export_folder, safe_name
from rushes.interchange import validate_entries
from rushes.models import Asset, Collection, CollectionItem, Export, Job, MediaTimeline, Project
from rushes.storage import StorageError, require_space
from rushes.timing import Interval

router = APIRouter(prefix="/api/workspaces/{workspace_id}")


class ExportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal[
        "clips", "copies", "json", "csv", "selections_json", "selections_csv", "fcp7xml", "fcpxml"
    ]
    collection_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None
    start_us: int | None = Field(default=None, ge=0)
    end_us: int | None = Field(default=None, gt=0)


@router.post("/projects/{project_id}/export-preview", status_code=201)
async def preview_export(project_id: uuid.UUID, body: ExportInput, db: DB, access: Access):
    require_editor(access)
    await owned(db, Project, project_id, access)
    entries = []
    if body.kind in {"clips", "copies", "fcp7xml", "fcpxml", "selections_json", "selections_csv"}:
        if body.collection_id:
            collection = await owned(db, Collection, body.collection_id, access)
            if collection.project_id != project_id:
                raise HTTPException(422, "Collection belongs to a different project")
            items = [
                {"asset_id": item.asset_id, "start_us": item.start_us, "end_us": item.end_us}
                for item in await db.scalars(
                    select(CollectionItem)
                    .where(CollectionItem.collection_id == collection.id)
                    .order_by(CollectionItem.position, CollectionItem.created_at)
                    .limit(501)
                )
            ]
        elif body.asset_id:
            items = [{"asset_id": body.asset_id, "start_us": body.start_us, "end_us": body.end_us}]
        else:
            raise HTTPException(422, "Choose a source or collection to export")
        if not items:
            raise HTTPException(422, "This collection is empty")
        if len(items) > 500:
            raise HTTPException(
                422, "This export exceeds 500 items. Split the collection before exporting."
            )
        asset_ids = {item["asset_id"] for item in items}
        assets = {
            asset.id: asset
            for asset in await db.scalars(
                select(Asset).where(
                    Asset.id.in_(asset_ids), Asset.workspace_id == access.workspace_id
                )
            )
        }
        timelines = {
            timeline.asset_id: timeline
            for timeline in await db.scalars(
                select(MediaTimeline).where(
                    MediaTimeline.asset_id.in_(asset_ids),
                    MediaTimeline.workspace_id == access.workspace_id,
                    MediaTimeline.kind == "source",
                )
            )
        }
        if assets.keys() != asset_ids:
            raise HTTPException(404, "Record not found")
        for index, item in enumerate(items):
            asset = assets[item["asset_id"]]
            timeline = timelines.get(asset.id)
            if (
                asset.project_id != project_id
                or not asset.fingerprint
                or not asset.duration_us
                or timeline is None
            ):
                raise HTTPException(422, "Wait for a valid source preview before exporting")
            start = item["start_us"] if item["start_us"] is not None else 0
            end = item["end_us"] if item["end_us"] is not None else asset.duration_us
            try:
                Interval(start_us=start, end_us=end).within(asset.duration_us)
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
            if body.kind == "copies" and (start != 0 or end != asset.duration_us):
                raise HTTPException(
                    422,
                    "This collection contains selected ranges. Choose rendered clips, or change the items to full files.",
                )
            suffix = Path(asset.name).suffix if body.kind == "copies" else ".mp4"
            estimated = (
                asset.source_size if body.kind == "copies" else max(1_000_000, (end - start) * 2)
            )
            entries.append(
                {
                    "asset_id": str(asset.id),
                    "source_name": asset.name,
                    "source_root": asset.source_root,
                    "relative_path": asset.relative_path,
                    "import_relative_path": asset.import_relative_path,
                    "fingerprint": asset.fingerprint,
                    "timeline": timeline.details,
                    "start_us": start,
                    "end_us": end,
                    "mode": "copy" if body.kind == "copies" else "render",
                    "filename": f"{index + 1:04d}-{safe_name(asset.name)}{suffix}",
                    "estimated_bytes": estimated,
                }
            )
    if body.kind in {"fcp7xml", "fcpxml"}:
        try:
            validate_entries(entries)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        for entry in entries:
            entry["mode"] = "source reference"
            entry["estimated_bytes"] = 10000
    if body.kind.startswith("selections_"):
        for entry in entries:
            entry["mode"], entry["estimated_bytes"] = "selection data", 10000
    estimated_bytes = sum(entry["estimated_bytes"] for entry in entries) or 10_000_000
    root = settings().output_root
    try:
        require_space(root, estimated_bytes, settings().min_free_bytes)
    except StorageError as error:
        raise HTTPException(409, str(error)) from error
    job_id, export_id = uuid.uuid4(), uuid.uuid4()
    job = Job(
        id=job_id,
        workspace_id=access.workspace_id,
        project_id=project_id,
        kind="export",
        state="draft",
        stage="Review export preview",
        workflow_id=f"export:{export_id}",
    )
    db.add(job)
    await db.flush()
    export = Export(
        id=export_id,
        workspace_id=access.workspace_id,
        project_id=project_id,
        job_id=job_id,
        kind=body.kind,
        name=f"{body.kind.upper()} export",
        state="draft",
        plan={"entries": entries, "estimated_bytes": estimated_bytes, "schema": "render-plan-v1"},
    )
    db.add(export)
    return {
        "id": export_id,
        "kind": body.kind,
        "estimated_bytes": estimated_bytes,
        "output_folder": str(export_folder(access.workspace_id, export_id)),
        "collisions": [],
        "entries": [
            {
                key: entry[key]
                for key in ["asset_id", "source_name", "start_us", "end_us", "mode", "filename"]
            }
            for entry in entries
        ],
        "notice": (
            "Experimental straight-cut interchange. No target editor is installed for round-trip validation. References local source media; inspect timing and audio in your editor."
            if body.kind in {"fcp7xml", "fcpxml"}
            else "Originals stay intact. Clips are re-encoded using source presentation timestamps; semantic event locations remain approximate."
        ),
    }


@router.post("/exports/{export_id}/start", status_code=202)
async def start_export(export_id: uuid.UUID, db: DB, access: Access):
    require_editor(access)
    export = await owned(db, Export, export_id, access)
    if export.state == "draft":
        export.state = "queued"
        (await db.get(Job, export.job_id)).state = "queued"
    return {"id": export.id, "state": export.state}


@router.get("/projects/{project_id}/exports")
async def exports(project_id: uuid.UUID, db: DB, access: Access, offset: int = Query(0, ge=0)):
    await owned(db, Project, project_id, access)
    columns = [column for column in Export.__table__.columns if column.key != "plan"]
    rows = await db.execute(
        select(*columns)
        .where(Export.project_id == project_id, Export.state != "draft")
        .order_by(Export.created_at.desc(), Export.id)
        .offset(offset)
        .limit(100)
    )
    total = await db.scalar(
        select(func.count())
        .select_from(Export)
        .where(Export.project_id == project_id, Export.state != "draft")
    )
    return {"items": [dict(row) for row in rows.mappings()], "total": total}


@router.get("/exports/{export_id}/download/{index}")
async def download(export_id: uuid.UUID, index: int, db: DB, access: Access):
    export = await owned(db, Export, export_id, access)
    outputs = export.provenance.get("outputs", [])
    if export.state != "completed" or not 0 <= index < len(outputs):
        raise HTTPException(404, "Completed export file not found")
    folder = export_folder(access.workspace_id, export.id)
    path = (folder / outputs[index]["output"]).resolve()
    if not path.is_relative_to(folder.resolve()) or not path.is_file():
        raise HTTPException(404, "Export file is missing from its output folder")
    return FileResponse(path, filename=path.name)


@router.post("/exports/{export_id}/retry", status_code=202)
async def retry_export(export_id: uuid.UUID, db: DB, access: Access):
    require_editor(access)
    output = await owned(db, Export, export_id, access)
    job = await db.scalar(select(Job).where(Job.id == output.job_id).with_for_update())
    if job.state not in {"failed", "canceled"}:
        raise HTTPException(409, "Only failed or canceled exports can be retried")
    job.workflow_id = f"export:{output.id}:retry:{uuid.uuid4()}"
    job.state, job.error = "queued", None
    output.state = "queued"
    return {"state": "queued", "job_id": job.id}
