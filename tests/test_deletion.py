import asyncio
import threading
import uuid
from functools import wraps
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from rushes import activities, deletion, pipeline
from rushes.api import app
from rushes.config import settings
from rushes.db import session_factory, tenant_session
from rushes.deletion import workspace_file_lease
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
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def deletion_storage(tmp_path, monkeypatch):
    for field in ("storage_root", "output_root"):
        path = tmp_path / field
        path.mkdir()
        monkeypatch.setattr(settings(), field, path)
    monkeypatch.setattr(settings(), "min_free_bytes", 0)
    return tmp_path


async def graph(workspace_id, project_id):
    """A finished upload with all FK dependents, and genuine private bytes to reclaim."""
    asset_id, job_id = uuid.uuid4(), uuid.uuid4()
    uploaded = settings().storage_root / "uploads" / str(workspace_id) / str(asset_id)
    derived = settings().storage_root / str(workspace_id) / str(asset_id)
    uploaded.mkdir(parents=True)
    (derived / "old-preprocessing").mkdir(parents=True)
    (uploaded / "original.mp4").write_bytes(b"uploaded original bytes")
    (derived / "old-preprocessing/proxy.mp4").write_bytes(b"derived proxy")
    (derived / "thumbnail.jpg").write_bytes(b"thumbnail")
    async with tenant_session(workspace_id) as db:
        asset = Asset(
            id=asset_id,
            workspace_id=workspace_id,
            project_id=project_id,
            name="Deletion fixture.mp4",
            source_kind="uploaded",
            source_root=str(uploaded),
            relative_path="original.mp4",
            source_size=23,
            status="ready",
            duration_us=10_000_000,
            proxy_path=str(derived / "old-preprocessing/proxy.mp4"),
        )
        job = Job(
            id=job_id,
            workspace_id=workspace_id,
            project_id=project_id,
            asset_id=asset_id,
            kind="asset",
            state="ready",
            workflow_id=f"test-delete:{job_id}",
        )
        db.add(asset)
        await db.flush()
        db.add(job)
        timeline = MediaTimeline(workspace_id=workspace_id, asset_id=asset_id, details={})
        run = AnalysisRun(
            workspace_id=workspace_id,
            asset_id=asset_id,
            operation_key=f"analysis:{job_id}",
            model="fixture",
            prompt_version="fixture",
            preprocessing_version="fixture",
            schema_version="observations-v2",
            transcript_version="fixture",
            sampling={},
            status="ready",
        )
        collection = Collection(workspace_id=workspace_id, project_id=project_id, name="Fixture")
        db.add_all([timeline, run, collection])
        await db.flush()
        window = AnalysisWindow(
            workspace_id=workspace_id,
            run_id=run.id,
            asset_id=asset_id,
            start_us=0,
            end_us=10_000_000,
            cache_key=f"delete:{asset_id}",
            state="completed",
        )
        db.add(window)
        await db.flush()
        observation = Observation(
            workspace_id=workspace_id,
            asset_id=asset_id,
            timeline_id=timeline.id,
            run_id=run.id,
            window_id=window.id,
            operation_key=f"delete-observation:{asset_id}",
            kind="shot_description",
            start_us=0,
            end_us=10_000_000,
            proposed_start_us=0,
            proposed_end_us=10_000_000,
            description="Synthetic deletion evidence",
            producer="test",
            model="fixture",
            prompt_version="fixture",
            preprocessing_version="fixture",
        )
        reservation = Reservation(
            workspace_id=workspace_id,
            operation_key=f"analysis:{job_id}",
            amount_milli=100,
            settled_milli=60,
            state="settled",
        )
        db.add_all([observation, reservation])
        await db.flush()
        owner = (await db.get(Workspace, workspace_id)).owner_id
        db.add_all(
            [
                ObservationRevision(
                    workspace_id=workspace_id,
                    observation_id=observation.id,
                    user_id=owner,
                    version=1,
                    before={},
                    after={},
                ),
                Embedding(
                    workspace_id=workspace_id,
                    observation_id=observation.id,
                    model="fixture",
                    dimension=2,
                    text_hash="fixture",
                    vector=[0.1, 0.2],
                ),
                Shot(workspace_id=workspace_id, asset_id=asset_id, start_us=0, end_us=10_000_000),
                CollectionItem(
                    workspace_id=workspace_id, collection_id=collection.id, asset_id=asset_id
                ),
                ProcessingEvent(
                    workspace_id=workspace_id, job_id=job_id, kind="completed", message="Fixture"
                ),
                Usage(
                    workspace_id=workspace_id,
                    asset_id=asset_id,
                    operation_key=f"delete-usage:{asset_id}",
                    kind="analysis",
                    input_tokens=100,
                ),
                LedgerEntry(
                    workspace_id=workspace_id,
                    reservation_id=reservation.id,
                    operation_key=f"delete-ledger:{asset_id}",
                    kind="settled",
                    delta_milli=40,
                    balance_milli=1000,
                    description="Synthetic prior charge",
                ),
            ]
        )
    return {
        "asset": asset_id,
        "job": job_id,
        "window": window.id,
        "run": run.id,
        "observation": observation.id,
        "reservation": reservation.id,
        "collection": collection.id,
        "uploaded": uploaded,
        "derived": derived,
    }


async def export_record(workspace_id, project_id, asset_id, state="completed"):
    export_id, job_id = uuid.uuid4(), uuid.uuid4()
    folder = settings().output_root / str(workspace_id) / str(export_id)
    (folder / "waves").mkdir(parents=True)
    (folder / "waves/0001-original.mp4").write_bytes(b"completed exported copy")
    (folder / "provenance.json").write_bytes(b"{}")
    async with tenant_session(workspace_id) as db:
        db.add(
            Job(
                id=job_id,
                workspace_id=workspace_id,
                project_id=project_id,
                kind="export",
                state=state,
                workflow_id=f"test-delete-export:{export_id}",
            )
        )
        await db.flush()
        db.add(
            Export(
                id=export_id,
                workspace_id=workspace_id,
                project_id=project_id,
                job_id=job_id,
                name="Fixture export",
                kind="copies",
                state=state,
                output_path=str(folder),
                plan={"entries": [{"asset_id": str(asset_id)}]},
            )
        )
        db.add(
            ProcessingEvent(
                workspace_id=workspace_id, job_id=job_id, kind="completed", message="Fixture"
            )
        )
        db.add(
            Usage(
                workspace_id=workspace_id,
                operation_key=f"export:{export_id}",
                kind="export",
                bytes=23,
            )
        )
    return export_id, job_id, folder


async def assert_asset_removed(workspace_id, seeded):
    async with tenant_session(workspace_id) as db:
        assert await db.get(Asset, seeded["asset"]) is None
        assert await db.get(Job, seeded["job"]) is None
        assert await db.get(AnalysisWindow, seeded["window"]) is None
        assert await db.get(AnalysisRun, seeded["run"]) is None
        assert await db.get(Observation, seeded["observation"]) is None
    assert not seeded["uploaded"].exists()
    assert not seeded["derived"].exists()


async def test_asset_delete_cascades_reclaims_and_preserves_accounting_exports_and_duplicates(
    authenticated, deletion_storage
):
    clients, ws, _, project, base_asset, _ = authenticated
    seeded = await graph(ws, project)
    exported, _, folder = await export_record(ws, project, seeded["asset"])
    async with tenant_session(ws) as db:
        other = await db.get(Asset, base_asset)
        original = Path(other.source_root) / other.relative_path
        other.duplicate_of_id = seeded["asset"]
        balance = (await db.get(Workspace, ws)).balance_milli
    response = await clients[0].delete(f"/api/workspaces/{ws}/assets/{seeded['asset']}")
    assert response.status_code == 200, response.text
    assert response.json() == {"deleted": True, "reclaimed_bytes": 45, "deleted_files": 3}
    await assert_asset_removed(ws, seeded)
    assert original.read_bytes() == b"0123456789"
    assert (folder / "waves/0001-original.mp4").read_bytes() == b"completed exported copy"
    async with tenant_session(ws) as db:
        assert (await db.get(Asset, base_asset)).duplicate_of_id is None
        assert await db.get(Export, exported)
        assert await db.get(Collection, seeded["collection"])
        assert not await db.scalar(
            select(CollectionItem.id).where(CollectionItem.asset_id == seeded["asset"])
        )
        assert (await db.get(Reservation, seeded["reservation"])).settled_milli == 60
        assert (await db.get(Workspace, ws)).balance_milli == balance
        usage = await db.scalar(
            select(Usage).where(Usage.operation_key == f"delete-usage:{seeded['asset']}")
        )
        assert usage.asset_id is None and usage.input_tokens == 100
    assert (
        await clients[0].delete(f"/api/workspaces/{ws}/assets/{seeded['asset']}")
    ).status_code == 404


@pytest.mark.parametrize("scope", ["project", "workspace"])
async def test_container_delete_removes_all_owned_records_and_bytes_only(
    authenticated, deletion_storage, scope
):
    clients, ws, other_ws, project, base_asset, _ = authenticated
    seeded = await graph(ws, project)
    _, _, export_folder = await export_record(ws, project, seeded["asset"])
    async with tenant_session(ws) as db:
        asset = await db.get(Asset, base_asset)
        indexed_original = Path(asset.source_root) / asset.relative_path
    async with session_factory()() as db:
        provider_before = await db.scalar(text("SELECT count(*) FROM provider_spend_reservation"))
    url = f"/api/workspaces/{ws}" + (f"/projects/{project}" if scope == "project" else "")
    response = await clients[0].delete(url)
    assert response.status_code == 200, response.text
    await assert_asset_removed(ws, seeded)
    assert not export_folder.exists()
    assert indexed_original.read_bytes() == b"0123456789"
    async with tenant_session(ws) as db:
        for model in (
            Project,
            Asset,
            Job,
            Export,
            Collection,
            CollectionItem,
            ObservationRevision,
            Embedding,
            ProcessingEvent,
        ):
            assert (
                await db.scalar(
                    select(func.count()).select_from(model).where(model.workspace_id == ws)
                )
                == 0
            )
        assert bool(await db.get(Reservation, seeded["reservation"])) == (scope == "project")
    async with session_factory()() as db:
        assert bool(await db.get(Workspace, ws)) == (scope == "project")
        assert await db.get(Workspace, other_ws)
        assert (
            await db.scalar(text("SELECT count(*) FROM provider_spend_reservation"))
            == provider_before
        )
        membership_count = await db.scalar(
            select(func.count()).select_from(Membership).where(Membership.workspace_id == ws)
        )
        assert membership_count == (2 if scope == "project" else 0)


@pytest.mark.parametrize("state", ["draft", "completed", "failed", "canceled"])
async def test_export_delete_reclaims_nested_copies_receipts_and_preserves_source(
    authenticated, deletion_storage, state
):
    clients, ws, _, project, base_asset, _ = authenticated
    exported, job_id, folder = await export_record(ws, project, base_asset, state)
    response = await clients[0].delete(f"/api/workspaces/{ws}/exports/{exported}")
    assert response.status_code == 200, response.text
    assert response.json()["reclaimed_bytes"] == 25
    assert not folder.exists()
    async with tenant_session(ws) as db:
        assert await db.get(Export, exported) is None
        assert await db.get(Job, job_id) is None
        assert await db.get(Asset, base_asset)
        assert await db.scalar(select(Usage.id).where(Usage.operation_key == f"export:{exported}"))


@pytest.mark.parametrize("scope", ["workspace", "project", "asset", "export"])
async def test_delete_requires_membership_and_role(authenticated, deletion_storage, scope):
    clients, ws, other_ws, project, asset, _ = authenticated
    exported, _, _ = await export_record(ws, project, asset)
    suffix = {
        "workspace": "",
        "project": f"/projects/{project}",
        "asset": f"/assets/{asset}",
        "export": f"/exports/{exported}",
    }[scope]
    url = f"/api/workspaces/{ws}{suffix}"
    assert (await clients[1].delete(url)).status_code == 403
    assert (await clients[2].delete(url)).status_code == 404
    if scope != "workspace":
        assert (await clients[2].delete(f"/api/workspaces/{other_ws}{suffix}")).status_code == 404
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://localhost",
        headers={"Origin": settings().origin},
    ) as anonymous:
        assert (await anonymous.delete(url)).status_code == 401
    async with tenant_session(ws) as db:
        viewer = await db.scalar(
            select(Membership).where(Membership.workspace_id == ws, Membership.role == "viewer")
        )
        viewer.role = "editor"
    response = await clients[1].delete(url)
    assert response.status_code == (403 if scope == "workspace" else 200), response.text


@pytest.mark.parametrize("state", ["queued", "dispatched", "running", "cancel_requested"])
async def test_active_jobs_block_asset_project_and_workspace_deletion(
    authenticated, deletion_storage, state
):
    clients, ws, _, project, _, _ = authenticated
    seeded = await graph(ws, project)
    async with tenant_session(ws) as db:
        (await db.get(Job, seeded["job"])).state = state
    for suffix in (f"/assets/{seeded['asset']}", f"/projects/{project}", ""):
        response = await clients[0].delete(f"/api/workspaces/{ws}{suffix}")
        assert response.status_code == 409, response.text
        assert "Cancel" in response.json()["detail"]
    assert (seeded["uploaded"] / "original.mp4").exists()


async def test_unfinished_export_blocks_source_deletion_until_export_removed(
    authenticated, deletion_storage
):
    clients, ws, _, project, _, _ = authenticated
    seeded = await graph(ws, project)
    exported, _, _ = await export_record(ws, project, seeded["asset"], "draft")
    url = f"/api/workspaces/{ws}/assets/{seeded['asset']}"
    response = await clients[0].delete(url)
    assert response.status_code == 409 and "export preview" in response.json()["detail"]
    assert (await clients[0].delete(f"/api/workspaces/{ws}/exports/{exported}")).status_code == 200
    assert (await clients[0].delete(url)).status_code == 200


async def test_active_export_blocks_its_deletion_and_project_source_deletion(
    authenticated, deletion_storage
):
    clients, ws, _, project, base_asset, _ = authenticated
    exported, _, _ = await export_record(ws, project, base_asset, "running")
    for suffix in (f"/exports/{exported}", f"/assets/{base_asset}"):
        assert (await clients[0].delete(f"/api/workspaces/{ws}{suffix}")).status_code == 409


@pytest.mark.parametrize("pending", ["provider", "credits", "in_flight"])
async def test_cleanup_and_settlement_records_cannot_be_discarded(
    authenticated, deletion_storage, pending
):
    clients, ws, _, project, _, _ = authenticated
    seeded = await graph(ws, project)
    async with tenant_session(ws) as db:
        if pending == "credits":
            (await db.get(Reservation, seeded["reservation"])).state = "reserved"
        else:
            window = await db.get(AnalysisWindow, seeded["window"])
            if pending == "provider":
                window.provider_file = "files/synthetic-cleanup-pending"
            else:
                window.state = "in_flight"
    response = await clients[0].delete(f"/api/workspaces/{ws}/assets/{seeded['asset']}")
    assert response.status_code == 409
    assert (seeded["uploaded"] / "original.mp4").exists()
    async with tenant_session(ws) as db:
        assert await db.get(AnalysisWindow, seeded["window"])
        # Never leave fake cleanup metadata for the real maintenance worker.
        (await db.get(AnalysisWindow, seeded["window"])).provider_file = None


async def test_upload_lease_and_database_work_block_deletion(authenticated, deletion_storage):
    clients, ws, _, project, _, _ = authenticated
    url = f"/api/workspaces/{ws}/projects/{project}"
    with workspace_file_lease(ws):
        response = await clients[0].delete(url)
        assert response.status_code == 409 and "upload" in response.json()["detail"]
    async with tenant_session(ws):
        response = await clients[0].delete(url)
        assert response.status_code == 409 and "activity" in response.json()["detail"]


async def test_streaming_upload_holds_lease_until_asset_publication(
    authenticated, deletion_storage
):
    clients, ws, _, project, _, _ = authenticated

    async def body():
        response = await clients[0].delete(f"/api/workspaces/{ws}/projects/{project}")
        assert response.status_code == 409
        yield b"synthetic-upload-bytes"

    response = await clients[0].post(
        f"/api/workspaces/{ws}/projects/{project}/upload?filename=fixture.mp4", content=body()
    )
    assert response.status_code == 202, response.text
    async with tenant_session(ws) as db:
        assert await db.get(Asset, uuid.UUID(response.json()["asset_id"]))
    with workspace_file_lease(ws, exclusive=True):
        response = await clients[0].post(
            f"/api/workspaces/{ws}/projects/{project}/upload?filename=other.mp4", content=b"bytes"
        )
        assert response.status_code == 409


async def test_symlink_target_rejected_before_any_rows_or_other_bytes_removed(
    authenticated, deletion_storage
):
    clients, ws, _, project, _, _ = authenticated
    seeded = await graph(ws, project)
    external = deletion_storage / "external"
    external.mkdir()
    (external / "original.mp4").write_bytes(b"must survive")
    for child in seeded["uploaded"].iterdir():
        child.unlink()
    seeded["uploaded"].rmdir()
    seeded["uploaded"].symlink_to(external, target_is_directory=True)
    response = await clients[0].delete(f"/api/workspaces/{ws}/assets/{seeded['asset']}")
    assert response.status_code == 409
    assert (external / "original.mp4").read_bytes() == b"must survive"
    assert (seeded["derived"] / "thumbnail.jpg").exists()
    async with tenant_session(ws) as db:
        assert await db.get(Asset, seeded["asset"])


async def test_interior_symlinks_and_untrusted_path_fields_never_delete_external_files(
    authenticated, deletion_storage
):
    clients, ws, _, project, _, _ = authenticated
    seeded = await graph(ws, project)
    external = deletion_storage / "external"
    external.mkdir()
    victim = external / "original.mp4"
    victim.write_bytes(b"keep external original")
    (seeded["derived"] / "external-link").symlink_to(external, target_is_directory=True)
    async with tenant_session(ws) as db:
        asset = await db.get(Asset, seeded["asset"])
        asset.source_root = str(external)
        asset.proxy_path = asset.thumbnail_path = str(victim)
    response = await clients[0].delete(f"/api/workspaces/{ws}/assets/{seeded['asset']}")
    assert response.status_code == 200, response.text
    assert victim.read_bytes() == b"keep external original"
    await assert_asset_removed(ws, seeded)


async def test_unwritable_storage_keeps_records_and_preflights_all_folders(
    authenticated, deletion_storage
):
    clients, ws, _, project, _, _ = authenticated
    seeded = await graph(ws, project)
    seeded["uploaded"].chmod(0o500)
    try:
        response = await clients[0].delete(f"/api/workspaces/{ws}/assets/{seeded['asset']}")
        assert response.status_code == 409
        assert (seeded["derived"] / "thumbnail.jpg").exists()
        assert (seeded["uploaded"] / "original.mp4").exists()
        async with tenant_session(ws) as db:
            assert await db.get(Asset, seeded["asset"])
    finally:
        seeded["uploaded"].chmod(0o700)


async def test_canceled_prepare_keeps_deletion_blocked_until_real_thread_stops(
    authenticated, deletion_storage, monkeypatch
):
    clients, ws, _, project, _, _ = authenticated
    seeded = await graph(ws, project)
    entered, release = threading.Event(), threading.Event()

    def slow_prepare(*args):
        entered.set()
        assert release.wait(10), "Test did not release its held storage thread"
        # A probe can finish after cancellation and create its output late.
        (seeded["derived"] / "late-probe-output").write_bytes(b"late")
        return {}

    monkeypatch.setattr(pipeline, "_prepare", slow_prepare)
    monkeypatch.setattr(activities, "heartbeat", lambda *args: None)
    async with tenant_session(ws) as db:
        (await db.get(Job, seeded["job"])).state = "dispatched"
    args = {"workspace_id": str(ws), "asset_id": str(seeded["asset"]), "job_id": str(seeded["job"])}
    task = asyncio.create_task(activities.prepare(args))
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        async with tenant_session(ws) as db:
            await activities.finalize_failure(
                db, {**args, "state": "canceled", "error": "Synthetic cancel"}
            )
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()  # A second cancellation must not release the actual thread's lease.
        await asyncio.sleep(0)
        response = await clients[0].delete(f"/api/workspaces/{ws}/assets/{seeded['asset']}")
        assert response.status_code == 409, response.text
        assert not task.done()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert (seeded["derived"] / "late-probe-output").exists()
    response = await clients[0].delete(f"/api/workspaces/{ws}/assets/{seeded['asset']}")
    assert response.status_code == 200, response.text
    await assert_asset_removed(ws, seeded)
    # Late activity retries cannot recreate a deleted folder or its failure record.
    with pytest.raises(ValueError, match="deleted"):
        await activities.prepare(args)
    async with tenant_session(ws) as db:
        await activities.finalize_failure(db, {**args, "state": "failed", "error": "Late retry"})
    assert not seeded["derived"].exists()


async def test_foreign_references_are_rejected_and_other_tenant_usage_survives_deletion(
    authenticated, deletion_storage
):
    clients, ws, other_ws, project, _, _ = authenticated
    seeded = await graph(ws, project)
    # The existing composite FK rejects an association that could cross the deletion boundary.
    with pytest.raises(IntegrityError):
        async with tenant_session(other_ws) as db:
            db.add(
                Usage(
                    workspace_id=other_ws,
                    asset_id=seeded["asset"],
                    operation_key=f"foreign-delete-guard:{uuid.uuid4()}",
                    kind="source",
                )
            )
    async with tenant_session(other_ws) as db:
        usage = Usage(
            workspace_id=other_ws,
            operation_key=f"foreign-delete-guard:{uuid.uuid4()}",
            kind="source",
        )
        db.add(usage)
    response = await clients[0].delete(f"/api/workspaces/{ws}/assets/{seeded['asset']}")
    assert response.status_code == 200, response.text
    await assert_asset_removed(ws, seeded)
    async with tenant_session(other_ws) as db:
        assert await db.get(Usage, usage.id)


async def test_export_storage_path_is_computed_from_ids_not_stored_output_path(
    authenticated, deletion_storage
):
    clients, ws, _, project, asset, _ = authenticated
    exported, _, folder = await export_record(ws, project, asset)
    outside = deletion_storage / "external-original.mp4"
    outside.write_bytes(b"never remove")
    async with tenant_session(ws) as db:
        (await db.get(Export, exported)).output_path = str(outside)
    response = await clients[0].delete(f"/api/workspaces/{ws}/exports/{exported}")
    assert response.status_code == 200, response.text
    assert outside.read_bytes() == b"never remove"
    assert not folder.exists()


async def test_partial_disk_failure_is_reported_truthfully_and_deletion_can_retry(
    authenticated, deletion_storage, monkeypatch
):
    clients, ws, _, project, _, _ = authenticated
    seeded = await graph(ws, project)
    original_remove = deletion.shutil.rmtree
    calls = 0

    @wraps(original_remove)
    def interrupted_remove(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise PermissionError("Synthetic disk failure after the first directory")
        return original_remove(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(deletion.shutil, "rmtree", interrupted_remove)
        response = await clients[0].delete(f"/api/workspaces/{ws}/assets/{seeded['asset']}")
    assert response.status_code == 409
    assert "still listed" in response.json()["detail"]
    assert "some files may already be removed" in response.json()["detail"]
    assert not seeded["derived"].exists()
    assert (seeded["uploaded"] / "original.mp4").exists()
    async with tenant_session(ws) as db:
        assert await db.get(Asset, seeded["asset"])
        assert await db.get(Observation, seeded["observation"])
    response = await clients[0].delete(f"/api/workspaces/{ws}/assets/{seeded['asset']}")
    assert response.status_code == 200, response.text
    await assert_asset_removed(ws, seeded)
