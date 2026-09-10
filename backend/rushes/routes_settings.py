import asyncio
import shutil
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select
from temporalio.client import Client

from rushes.api_common import DB, Access, owned, row_json
from rushes.auth import require_editor
from rushes.config import settings
from rushes.credits import estimate_milli
from rushes.job_actions import queue_asset
from rushes.models import Asset, Job, LedgerEntry, Membership, Usage, User, Workspace
from rushes.routes_media import root_at
from rushes.storage import StorageError, authorized_source_root, fingerprint, open_source

router = APIRouter(prefix="/api/workspaces/{workspace_id}")


@router.get("/settings")
async def workspace_settings(db: DB, access: Access):
    config = settings()
    storage = config.storage_root
    storage.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(storage)
    temporal_ready = False
    try:
        await asyncio.wait_for(Client.connect(config.temporal_address), timeout=2)
        temporal_ready = True
    except Exception:
        pass
    workspace = await db.get(Workspace, access.workspace_id)
    return {
        "workspace": {"id": workspace.id, "name": workspace.name, "role": access.role},
        "storage_root": str(storage),
        "output_root": str(config.output_root),
        "disk_free_bytes": usage.free,
        "minimum_free_bytes": config.min_free_bytes,
        "source_roots": [str(path) for path in config.source_roots],
        "gemini_configured": bool(
            config.gemini_api_key and config.gemini_api_key.get_secret_value()
        ),
        "gemini_model": config.gemini_model,
        "transcription_model": config.transcription_model,
        "embedding_model": config.embedding_model,
        "compute_backend": config.compute_backend,
        "temporal_connected": temporal_ready,
        "media_tools_available": bool(shutil.which("ffmpeg") and shutil.which("ffprobe")),
        "balance_milli": workspace.balance_milli,
        "credits_per_minute": config.credits_per_minute,
        "max_analysis_credits": config.max_analysis_credits,
        "payments_enabled": False,
        "analytics_enabled": False,
    }


@router.get("/usage")
async def usage(db: DB, access: Access):
    rows = await db.execute(
        select(
            Usage.kind,
            func.sum(Usage.duration_us),
            func.sum(Usage.bytes),
            func.sum(Usage.input_tokens),
            func.sum(Usage.output_tokens),
            func.sum(Usage.attempts),
        )
        .where(Usage.workspace_id == access.workspace_id)
        .group_by(Usage.kind)
    )
    unique_sources = (
        select(Asset.fingerprint, func.max(Asset.duration_us).label("duration"))
        .where(Asset.workspace_id == access.workspace_id, Asset.fingerprint.is_not(None))
        .group_by(Asset.fingerprint)
        .subquery()
    )
    unique_duration = await db.scalar(select(func.sum(unique_sources.c.duration)))
    entries = await db.scalars(
        select(LedgerEntry)
        .where(LedgerEntry.workspace_id == access.workspace_id)
        .order_by(LedgerEntry.created_at.desc())
        .limit(100)
    )
    return {
        "unique_source_duration_us": unique_duration or 0,
        "metrics": [
            {
                "kind": kind,
                "duration_us": duration or 0,
                "bytes": bytes or 0,
                "input_tokens": inputs or 0,
                "output_tokens": outputs or 0,
                "attempts": attempts or 0,
            }
            for kind, duration, bytes, inputs, outputs, attempts in rows
        ],
        "ledger": [row_json(entry) for entry in entries],
    }


@router.get("/members")
async def members(db: DB, access: Access):
    if access.role != "owner":
        raise HTTPException(403, "Only the workspace owner can manage membership")
    rows = await db.execute(
        select(Membership, User)
        .join(User, Membership.user_id == User.id)
        .where(Membership.workspace_id == access.workspace_id)
        .limit(200)
    )
    return [
        {"id": member.id, "email": user.email, "name": user.name, "role": member.role}
        for member, user in rows
    ]


class MemberInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    role: str = Field(pattern="^(editor|viewer)$")


@router.post("/members", status_code=201)
async def add_member(body: MemberInput, db: DB, access: Access):
    if access.role != "owner":
        raise HTTPException(403, "Only the workspace owner can manage membership")
    await db.scalar(select(Workspace).where(Workspace.id == access.workspace_id).with_for_update())
    user = await db.scalar(select(User).where(func.lower(User.email) == str(body.email).lower()))
    if not user:
        raise HTTPException(
            404, "This person must first create an account on this local RUSHES instance"
        )
    existing = await db.scalar(
        select(Membership).where(
            Membership.workspace_id == access.workspace_id, Membership.user_id == user.id
        )
    )
    if existing:
        if existing.role == "owner":
            raise HTTPException(409, "The workspace owner role cannot be changed here")
        existing.role = body.role
    else:
        count = await db.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.workspace_id == access.workspace_id)
        )
        if count >= 200:
            raise HTTPException(
                422, "Workspaces support up to 200 members. Remove a member before adding another."
            )
        db.add(Membership(workspace_id=access.workspace_id, user_id=user.id, role=body.role))
    return {"email": user.email, "role": body.role}


@router.delete("/members/{member_id}", status_code=204)
async def remove_member(member_id: uuid.UUID, db: DB, access: Access):
    if access.role != "owner":
        raise HTTPException(403, "Only the workspace owner can manage membership")
    membership = await owned(db, Membership, member_id, access)
    if membership.role == "owner":
        raise HTTPException(409, "The workspace owner cannot be removed")
    await db.delete(membership)


@router.get("/assets/{asset_id}/source-status")
async def source_status(asset_id: uuid.UUID, db: DB, access: Access):
    import os

    asset = await owned(db, Asset, asset_id, access)
    try:
        with open_source(
            authorized_source_root(asset.source_root, asset.workspace_id, asset.id),
            asset.relative_path,
        ) as source:
            stat = os.fstat(source.fileno())
        changed = (stat.st_size, stat.st_mtime_ns) != (asset.source_size, asset.source_mtime_ns)
        return {
            "state": "changed" if changed else "available",
            "verification": "size and modification time",
            "relative_path": asset.relative_path,
        }
    except StorageError:
        return {"state": "missing", "relative_path": asset.relative_path}


class RelinkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root: int = Field(ge=0)
    relative_path: str = Field(min_length=1, max_length=2000)


@router.post("/assets/{asset_id}/relink")
async def relink(asset_id: uuid.UUID, body: RelinkInput, db: DB, access: Access):
    import os

    require_editor(access)
    asset = await owned(db, Asset, asset_id, access)
    root = root_at(body.root)

    def verify():
        with open_source(root, body.relative_path) as file:
            return fingerprint(file), os.fstat(file.fileno())

    try:
        digest, stat = await asyncio.to_thread(verify)
    except StorageError as error:
        raise HTTPException(422, str(error)) from error
    if not asset.fingerprint or digest != asset.fingerprint:
        raise HTTPException(
            409, "Replacement bytes do not match this source. Import it as a new asset."
        )
    asset.source_root, asset.relative_path = str(root), body.relative_path
    asset.source_size, asset.source_mtime_ns = stat.st_size, stat.st_mtime_ns
    return {"id": asset.id, "state": "relinked", "verification": "SHA-256 content match"}


@router.get("/assets/{asset_id}/analysis-estimate")
async def analysis_estimate(asset_id: uuid.UUID, db: DB, access: Access):
    require_editor(access)
    asset = await owned(db, Asset, asset_id, access)
    config = settings()
    return {
        "amount_milli": estimate_milli(asset.duration_us or 0),
        "duration_us": asset.duration_us,
        "fingerprint": asset.fingerprint,
        "model": config.gemini_model,
        "available": bool(config.gemini_api_key and config.gemini_api_key.get_secret_value()),
        "notice": "User-requested reanalysis may use additional credits. Existing corrections are preserved.",
    }


class AnalysisConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount_milli: int = Field(ge=0)
    model: str
    fingerprint: str


@router.post("/assets/{asset_id}/reanalyze", status_code=202)
async def reanalyze(asset_id: uuid.UUID, body: AnalysisConfirmation, db: DB, access: Access):
    require_editor(access)
    asset = await db.scalar(select(Asset).where(Asset.id == asset_id).with_for_update())
    if asset is None:
        raise HTTPException(404, "Asset not found")
    config = settings()
    if not config.gemini_api_key or not config.gemini_api_key.get_secret_value():
        raise HTTPException(409, "Configure a Gemini key in the local environment first")
    if (
        not asset.duration_us
        or body.amount_milli != estimate_milli(asset.duration_us)
        or body.model != config.gemini_model
        or body.fingerprint != asset.fingerprint
    ):
        raise HTTPException(
            409, "Analysis estimate changed. Review a fresh estimate before starting."
        )
    if await db.scalar(
        select(Job.id)
        .where(
            Job.asset_id == asset.id,
            Job.state.in_(["queued", "dispatched", "running", "cancel_requested"]),
        )
        .limit(1)
    ):
        raise HTTPException(409, "This source already has an active job")
    job = queue_asset(db, asset, payload={"analysis_confirmation": body.model_dump()})
    asset.status = "queued"
    return {"job_id": job.id, "state": "queued"}
