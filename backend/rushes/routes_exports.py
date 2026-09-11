import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import cast, func, literal, select, type_coerce
from sqlalchemy.dialects.postgresql import JSONB, aggregate_order_by

from rushes.api_common import DB, Access, owned
from rushes.auth import require_editor
from rushes.config import settings
from rushes.exports import export_folder, safe_name
from rushes.interchange import validate_entries
from rushes.models import (
    Asset,
    Collection,
    CollectionItem,
    Export,
    Job,
    MediaTimeline,
    Observation,
    Project,
    now,
)
from rushes.organization import (
    CATEGORY_SLUG_PATTERN,
    ORGANIZATION_VERSION,
    category_asset_ids,
    organization_memberships,
)
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
    category: str | None = Field(default=None, max_length=36, pattern=CATEGORY_SLUG_PATTERN)
    start_us: int | None = Field(default=None, ge=0)
    end_us: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def category_selection(self):
        if (
            sum(value is not None for value in (self.collection_id, self.asset_id, self.category))
            > 1
        ):
            raise ValueError("Choose one source, collection, or category")
        if self.category is not None and (
            self.kind != "copies" or self.start_us is not None or self.end_us is not None
        ):
            raise ValueError("Category exports must copy full original files")
        return self


@router.post("/projects/{project_id}/export-preview", status_code=201)
async def preview_export(project_id: uuid.UUID, body: ExportInput, db: DB, access: Access):
    require_editor(access)
    await owned(db, Project, project_id, access)
    entries = []
    organization = None
    category_evidence = {}
    evidence_counts = {}
    if body.kind in {"clips", "copies", "fcp7xml", "fcpxml", "selections_json", "selections_csv"}:
        if body.category is not None:
            ids = await category_asset_ids(db, access.workspace_id, project_id, body.category)
            items = [{"asset_id": id, "start_us": None, "end_us": None} for id in ids]
        elif body.collection_id:
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
            raise HTTPException(422, "Choose a source, collection, or category to export")
        if not items:
            raise HTTPException(
                422,
                "This category has no matching files"
                if body.category
                else "This collection is empty",
            )
        if len(items) > 500:
            raise HTTPException(
                422, "This export exceeds 500 files. Choose a smaller category or collection."
            )
        asset_ids = {item["asset_id"] for item in items}
        if body.category is not None:
            organization = {
                "version": ORGANIZATION_VERSION,
                "category_id": body.category,
                "snapshot_at": now().isoformat(),
            }
            memberships = organization_memberships(access.workspace_id, project_id)
            matches = (
                select(
                    memberships.c.asset_id,
                    memberships.c.observation_id,
                    func.min(memberships.c.category_name).label("category_name"),
                )
                .where(
                    memberships.c.asset_id.in_(asset_ids),
                    memberships.c.category_id == body.category,
                )
                .group_by(memberships.c.asset_id, memberships.c.observation_id)
                .cte("category_export_matches")
            )
            ranked = (
                select(
                    matches,
                    func.row_number()
                    .over(
                        partition_by=matches.c.asset_id,
                        order_by=(Observation.start_us, Observation.id),
                    )
                    .label("rank"),
                    func.count().over(partition_by=matches.c.asset_id).label("evidence_count"),
                )
                .join(Observation, Observation.id == matches.c.observation_id)
                .where(Observation.workspace_id == access.workspace_id)
                .cte("category_export_ranked")
            )
            evidence = await db.execute(
                select(Observation, ranked.c.category_name, ranked.c.evidence_count)
                .join(ranked, ranked.c.observation_id == Observation.id)
                .where(ranked.c.rank <= 20, Observation.workspace_id == access.workspace_id)
                .order_by(Observation.asset_id, Observation.start_us, Observation.id)
            )
            for observation, category_name, evidence_count in evidence:
                evidence_counts[observation.asset_id] = evidence_count
                category_evidence.setdefault(observation.asset_id, []).append(
                    {
                        "observation_id": str(observation.id),
                        "run_id": str(observation.run_id),
                        "window_id": str(observation.window_id),
                        "version": observation.version,
                        "category_name": category_name,
                        "start_us": observation.start_us,
                        "end_us": observation.end_us,
                        "description": observation.description,
                        "evidence": observation.evidence,
                        "producer": observation.producer,
                        "model": observation.model,
                        "prompt_version": observation.prompt_version,
                        "preprocessing_version": observation.preprocessing_version,
                        "uncertainty": observation.uncertainty,
                        "review_status": observation.review_status,
                    }
                )
            if body.category != "uncategorized" and category_evidence.keys() != asset_ids:
                raise HTTPException(
                    409, "Category membership changed. Review a new export preview."
                )
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
                    "filename": f"{body.category + '/' if body.category else ''}{index + 1:04d}-{safe_name(asset.name)}{suffix}",
                    "estimated_bytes": estimated,
                    **(
                        {
                            "organization": {
                                **organization,
                                "evidence": category_evidence.get(asset.id, []),
                                "evidence_count": evidence_counts.get(asset.id, 0),
                                "evidence_truncated": evidence_counts.get(asset.id, 0) > 20,
                            }
                        }
                        if organization
                        else {}
                    ),
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
        name=f"{body.category} category export" if body.category else f"{body.kind.upper()} export",
        state="draft",
        plan={
            "entries": entries,
            "estimated_bytes": estimated_bytes,
            "schema": "render-plan-v1",
            **({"organization": organization} if organization else {}),
        },
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
            else "Full original files are copied byte for byte into a separate export folder. Originals remain unmodified."
            if body.kind == "copies"
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
    columns = [
        column for column in Export.__table__.columns if column.key not in {"plan", "provenance"}
    ]
    outputs = (
        func.jsonb_array_elements(Export.provenance["outputs"])
        .table_valued("value", with_ordinality="position")
        .render_derived(name="export_outputs")
    )
    value = type_coerce(outputs.c.value, JSONB)
    # Keep evidence on the server; output order must match download-by-index links.
    compact_outputs = (
        select(
            func.coalesce(
                func.jsonb_agg(
                    aggregate_order_by(
                        func.jsonb_build_object("output", value["output"], "bytes", value["bytes"]),
                        outputs.c.position,
                    )
                ),
                cast(literal("[]"), JSONB),
            )
        )
        .select_from(outputs)
        .correlate(Export)
        .scalar_subquery()
    )
    rows = await db.execute(
        select(*columns, func.jsonb_build_object("outputs", compact_outputs).label("provenance"))
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
