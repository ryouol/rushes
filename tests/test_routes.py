import uuid

import pytest
from rushes.auth import stream_access
from rushes.credits import reserve, settle
from rushes.db import tenant_session
from rushes.models import (
    Asset,
    Embedding,
    Job,
    LedgerEntry,
    Workspace,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request


@pytest.mark.integration
async def test_media_ranges_roles_note_corrections_and_session_revocation(authenticated):
    clients, ws, other, project, asset, tokens = authenticated
    owner, viewer, outsider = clients
    base = f"/api/workspaces/{ws}"
    response = await owner.get(f"{base}/assets/{asset}/media/proxy", headers={"Range": "bytes=2-5"})
    assert response.status_code == 206 and response.content == b"2345"
    body = {
        "description": "A synthetic note",
        "start_us": 2_000_000,
        "end_us": 4_000_000,
        "request_id": str(uuid.uuid4()),
    }
    for path in [
        f"/assets/{asset}",
        f"/assets/{asset}/media/proxy",
        f"/assets/{asset}/observations",
        f"/projects/{project}/search?q=note",
        "/events",
        "/usage",
    ]:
        assert (await outsider.get(base + path)).status_code == 404
    assert (await viewer.post(f"{base}/assets/{asset}/observations", json=body)).status_code == 403
    first = await owner.post(f"{base}/assets/{asset}/observations", json=body)
    assert first.status_code == 201, first.text
    note = first.json()
    again = await owner.post(f"{base}/assets/{asset}/observations", json=body)
    assert again.json()["id"] == note["id"]
    async with tenant_session(ws) as db:
        db.add(
            Embedding(
                workspace_id=ws,
                observation_id=uuid.UUID(note["id"]),
                model="test-old-model",
                dimension=2,
                text_hash="stale",
                vector=[0.1, 0.2],
            )
        )
    correction = {
        "description": "Corrected synthetic evidence",
        "start_us": 1_000_000,
        "end_us": 3_000_000,
        "version": 1,
    }
    assert (
        await viewer.patch(f"{base}/observations/{note['id']}", json=correction)
    ).status_code == 403
    result = await owner.patch(f"{base}/observations/{note['id']}", json=correction)
    assert result.status_code == 200, result.text
    assert result.json()["proposed_start_us"] == 2_000_000
    assert (
        await owner.patch(f"{base}/observations/{note['id']}", json=correction)
    ).status_code == 409
    history = (await owner.get(f"{base}/observations/{note['id']}/history")).json()
    assert len(history) == 1 and history[0]["before"]["description"] == body["description"]
    async with tenant_session(ws) as db:
        assert (
            await db.scalar(
                select(Embedding.id).where(
                    Embedding.observation_id == uuid.UUID(note["id"]),
                    Embedding.model == "test-old-model",
                )
            )
            is None
        )
    request = Request(
        {"type": "http", "headers": [(b"cookie", f"rushes_session={tokens[0]}".encode())]}
    )
    assert (await stream_access(request, ws)).workspace_id == ws
    await owner.post("/api/auth/logout")
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        await stream_access(request, ws)
    assert error.value.status_code == 401


@pytest.mark.integration
async def test_recovery_preserves_job_operation_and_settlement(authenticated):
    clients, ws, other, project, asset, _ = authenticated
    async with tenant_session(ws) as db:
        job = Job(
            workspace_id=ws,
            project_id=project,
            asset_id=asset,
            kind="asset",
            state="failed",
            workflow_id=f"test:{uuid.uuid4()}",
            payload={
                "analysis_confirmation": {"model": "reviewed-model", "amount_milli": 500},
                "batch_id": str(uuid.uuid4()),
            },
        )
        db.add(job)
        await db.flush()
        id = job.id
        await reserve(db, ws, f"analysis:{id}", 500)
        await settle(db, ws, f"analysis:{id}", 300)
    base = f"/api/workspaces/{ws}"
    response = await clients[0].post(f"{base}/assets/{asset}/retry")
    assert response.status_code == 202, response.text
    assert response.json()["job_id"] == str(id)
    assert (await clients[0].post(f"{base}/assets/{asset}/retry")).status_code == 409
    async with tenant_session(ws) as db:
        retried = await db.get(Job, id)
        assert retried.payload["analysis_confirmation"] == {
            "model": "reviewed-model",
            "amount_milli": 500,
        }
        assert "batch_id" not in retried.payload
        rows = list(await db.scalars(select(LedgerEntry).where(LedgerEntry.workspace_id == ws)))
        assert len(rows) == 2
        assert (await db.get(Workspace, ws)).balance_milli == 700
    # A same-tenant ID cannot be combined with a parent in another tenant, even under raw SQL access.
    with pytest.raises(IntegrityError):
        async with tenant_session(other) as db:
            db.add(
                Asset(
                    workspace_id=other,
                    project_id=project,
                    name="Forbidden",
                    source_root="/tmp",
                    relative_path="x",
                )
            )
            await db.flush()


@pytest.mark.integration
async def test_inflight_provider_request_is_recorded_ambiguous_without_repeat(
    authenticated, monkeypatch
):
    from rushes import activities
    from rushes.models import AnalysisRun, AnalysisWindow, Usage

    _clients, ws, _other, project, asset, _tokens = authenticated
    async with tenant_session(ws) as db:
        job = Job(
            workspace_id=ws,
            project_id=project,
            asset_id=asset,
            kind="asset",
            state="running",
            workflow_id=f"test:{uuid.uuid4()}",
        )
        db.add(job)
        await db.flush()
        job_id = job.id
        run = AnalysisRun(
            workspace_id=ws,
            asset_id=asset,
            operation_key=f"test:{uuid.uuid4()}",
            model="synthetic-provider-interface-test",
            prompt_version="test",
            preprocessing_version="test",
            schema_version="test",
            transcript_version="test",
            sampling={},
        )
        db.add(run)
        await db.flush()
        window = AnalysisWindow(
            workspace_id=ws,
            asset_id=asset,
            run_id=run.id,
            start_us=0,
            end_us=1_000_000,
            cache_key=str(uuid.uuid4()),
            state="in_flight",
            attempts=1,
        )
        db.add(window)
        await db.flush()
        id = window.id
    monkeypatch.setattr(activities, "heartbeat", lambda *_: None)

    async def stage(*_):
        pass

    monkeypatch.setattr(activities, "stage", stage)

    def never_send(*_):
        raise AssertionError("An uncertain provider request must not be repeated")

    monkeypatch.setattr(activities, "GeminiAnalyzer", never_send)
    args = {
        "workspace_id": str(ws),
        "asset_id": str(asset),
        "window_id": str(id),
        "job_id": str(job_id),
    }
    assert await activities.analyze_window(args) == "ambiguous"
    assert await activities.analyze_window(args) == "ambiguous"
    async with tenant_session(ws) as db:
        usage = list(
            await db.scalars(select(Usage).where(Usage.operation_key == f"ambiguous:{id}"))
        )
        assert len(usage) == 1 and usage[0].provider_outcome == "ambiguous"
