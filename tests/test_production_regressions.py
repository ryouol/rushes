import asyncio
import json
import uuid
from datetime import timedelta

import pytest
from pydantic import SecretStr
from rushes import maintenance, pipeline, routes_media
from rushes.auth import WorkspaceAccess
from rushes.config import settings
from rushes.db import session_factory, tenant_session
from rushes.models import (
    AnalysisRun,
    AnalysisWindow,
    Collection,
    CollectionItem,
    Export,
    Job,
    Membership,
    Project,
    User,
    now,
)
from rushes.timing import Interval
from sqlalchemy import select
from starlette.requests import Request


@pytest.mark.integration
async def test_project_and_export_history_are_paginated(authenticated):
    clients, ws, _other, project, _asset, _tokens = authenticated
    async with tenant_session(ws) as db:
        db.add_all([Project(workspace_id=ws, name=f"Synthetic project {i}") for i in range(41)])
        for i in range(101):
            job = Job(
                workspace_id=ws,
                project_id=project,
                kind="export",
                state="completed",
                workflow_id=f"test:{uuid.uuid4()}",
            )
            db.add(job)
            await db.flush()
            db.add(
                Export(
                    workspace_id=ws,
                    project_id=project,
                    job_id=job.id,
                    kind="json",
                    name=f"Synthetic export {i}",
                    state="completed",
                    plan={"private": "excluded"},
                )
            )
    base = f"/api/workspaces/{ws}/projects"
    pages = [(await clients[0].get(base + suffix)).json() for suffix in ("", "?offset=40")]
    assert pages[0]["total"] == pages[1]["total"] == 42
    assert len({row["id"] for page in pages for row in page["items"]}) == 42
    pages = [
        (await clients[0].get(f"{base}/{project}/exports{suffix}")).json()
        for suffix in ("", "?offset=100")
    ]
    assert pages[0]["total"] == pages[1]["total"] == 101
    assert len({row["id"] for page in pages for row in page["items"]}) == 101
    assert all("plan" not in row for page in pages for row in page["items"])


@pytest.mark.integration
async def test_partial_selection_patch_and_collection_limit(authenticated):
    clients, ws, _other, project, asset, _tokens = authenticated
    async with tenant_session(ws) as db:
        groups = [
            Collection(workspace_id=ws, project_id=project, name=f"Synthetic {i}")
            for i in range(200)
        ]
        db.add_all(groups)
        await db.flush()
        item = CollectionItem(
            workspace_id=ws,
            collection_id=groups[0].id,
            asset_id=asset,
            start_us=1_000_000,
            end_us=3_000_000,
            note="original",
        )
        db.add(item)
        await db.flush()
        item_id = item.id
    base = f"/api/workspaces/{ws}"
    response = await clients[0].patch(
        f"{base}/collection-items/{item_id}", json={"note": "updated"}
    )
    assert response.status_code == 200
    assert (response.json()["start_us"], response.json()["end_us"]) == (1_000_000, 3_000_000)
    assert (
        await clients[0].patch(f"{base}/collection-items/{item_id}", json={"start_us": 4_000_000})
    ).status_code == 422
    response = await clients[0].patch(
        f"{base}/collection-items/{item_id}", json={"end_us": 4_000_000}
    )
    assert response.json()["note"] == "updated"
    assert (
        await clients[0].post(f"{base}/projects/{project}/collections", json={"name": "Too many"})
    ).status_code == 422
    assert len((await clients[0].get(f"{base}/projects/{project}/collections")).json()) == 200


@pytest.mark.integration
@pytest.mark.parametrize("same_project_queue", [False, True])
async def test_project_events_retain_older_active_job(
    authenticated, monkeypatch, same_project_queue
):
    clients, ws, _other, project, asset, _tokens = authenticated
    async with tenant_session(ws) as db:
        other_project = Project(workspace_id=ws, name="Noisy synthetic project")
        db.add(other_project)
        await db.flush()
        active = Job(
            workspace_id=ws,
            project_id=project,
            asset_id=asset,
            kind="asset",
            state="running",
            workflow_id=f"test:{uuid.uuid4()}",
        )
        db.add(active)
        db.add_all(
            [
                Job(
                    workspace_id=ws,
                    project_id=project if same_project_queue else other_project.id,
                    kind="index",
                    state="queued" if same_project_queue else "completed",
                    workflow_id=f"test:{uuid.uuid4()}",
                )
                for _ in range(105)
            ]
        )
        await db.flush()
        active_id = str(active.id)

    async def access(*args):
        return WorkspaceAccess(ws, uuid.uuid4(), "owner")

    monkeypatch.setattr(routes_media, "stream_access", access)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request({"type": "http", "headers": []}, receive)
    response = await routes_media.events(request, ws, project)
    try:
        first = await anext(response.body_iterator)
        rows = json.loads(first.removeprefix("data: ").strip())
        assert rows[0]["id"] == active_id
        assert len(rows) == (100 if same_project_queue else 1)
    finally:
        await response.body_iterator.aclose()
    jobs = (await clients[0].get(f"/api/workspaces/{ws}/jobs")).json()
    assert jobs[0]["id"] == active_id


@pytest.mark.integration
async def test_member_limit_preserves_role_updates(authenticated):
    clients, ws, *_ = authenticated
    async with session_factory()() as db:
        users = [
            User(
                email=f"limit-{uuid.uuid4()}@example.com", hashed_password="unusable-test-password"
            )
            for _ in range(199)
        ]
        db.add_all(users)
        await db.flush()
        db.add_all(
            [Membership(workspace_id=ws, user_id=user.id, role="viewer") for user in users[:-1]]
        )
        existing_email, new_email = users[0].email, users[-1].email
        await db.commit()
    base = f"/api/workspaces/{ws}/members"
    assert (
        await clients[0].post(base, json={"email": new_email, "role": "viewer"})
    ).status_code == 422
    assert (
        await clients[0].post(base, json={"email": existing_email, "role": "editor"})
    ).status_code == 201
    members = (await clients[0].get(base)).json()
    assert len(members) == 200
    assert next(row for row in members if row["email"] == existing_email)["role"] == "editor"


@pytest.mark.integration
@pytest.mark.parametrize("replacement_fails", [False, True])
@pytest.mark.parametrize("offline_expiry", [False, True])
async def test_received_file_cleanup_delays_failures_and_reaches_newer_expired_files(
    authenticated, monkeypatch, replacement_fails, offline_expiry
):
    _clients, ws, _other, _project, asset, _tokens = authenticated
    monkeypatch.setattr(settings(), "gemini_api_key", SecretStr("synthetic-no-network"))
    async with tenant_session(ws) as db:
        run = AnalysisRun(
            workspace_id=ws,
            asset_id=asset,
            operation_key=str(uuid.uuid4()),
            model="synthetic",
            prompt_version="fixture",
            preprocessing_version="fixture",
            schema_version="fixture",
            transcript_version="fixture",
            sampling={},
        )
        db.add(run)
        await db.flush()
        for index in range(22):
            db.add(
                AnalysisWindow(
                    workspace_id=ws,
                    asset_id=asset,
                    run_id=run.id,
                    start_us=0,
                    end_us=1_000_000,
                    cache_key=str(uuid.uuid4()),
                    state="in_flight" if index == 21 else "received",
                    raw_response={"retained": True},
                    provider_file=f"files/synthetic-{index}",
                    provider_file_expires_at=now() - timedelta(minutes=1) if index >= 20 else None,
                    provider_file_retry_at=now() + timedelta(hours=1) if index >= 20 else None,
                    created_at=now() - timedelta(hours=3) + timedelta(seconds=index),
                )
            )
        run_id = run.id
    attempted = []

    original_delete = maintenance.delete_remote

    def delete(name, expiry):
        attempted.append(name)
        if int(name.rsplit("-", 1)[1]) < 20:
            raise RuntimeError("Synthetic transient provider error")
        original_delete(name, expiry)

    monkeypatch.setattr(maintenance, "delete_remote", delete)
    await maintenance.cleanup_provider_files(ws)
    assert attempted == [f"files/synthetic-{index}" for index in range(20)]

    async def end_pass(_seconds):
        raise asyncio.CancelledError()

    if offline_expiry:
        with monkeypatch.context() as offline:
            offline.setattr(settings(), "gemini_api_key", None)
            offline.setattr(maintenance, "unit_paths", lambda: iter(()))
            offline.setattr(maintenance.asyncio, "sleep", end_pass)
            with pytest.raises(asyncio.CancelledError):
                await maintenance.maintain()
    else:
        await maintenance.cleanup_provider_files(ws)
    assert attempted == [f"files/synthetic-{index}" for index in range(21)]
    async with tenant_session(ws) as db:
        rows = list(
            await db.scalars(
                select(AnalysisWindow)
                .where(AnalysisWindow.run_id == run_id)
                .order_by(AnalysisWindow.created_at)
            )
        )
        assert [row.provider_file for row in rows[:20]] == [
            f"files/synthetic-{i}" for i in range(20)
        ]
        assert all(row.provider_file_retry_at > now() for row in rows[:20])
        assert rows[20].provider_file is None
        assert rows[20].provider_file_expires_at is None
        assert rows[20].provider_file_retry_at is None
        assert rows[21].provider_file == "files/synthetic-21"
        assert all(
            row.state == "received" and row.raw_response == {"retained": True}
            for row in rows
            if row is not rows[21]
        )
        replaced_id = rows[0].id
        rows[0].provider_file_retry_at = None
    replacement_expiry = now() + timedelta(hours=48)

    async def concurrent_replacement(_function, name, _expiry):
        async with tenant_session(ws) as db:
            row = await db.get(AnalysisWindow, replaced_id)
            row.provider_file_expires_at = replacement_expiry
        if replacement_fails:
            raise RuntimeError("Synthetic stale attempt failed")

    monkeypatch.setattr(maintenance.asyncio, "to_thread", concurrent_replacement)
    await maintenance.cleanup_provider_files(ws)
    async with tenant_session(ws) as db:
        row = await db.get(AnalysisWindow, replaced_id)
        assert row.provider_file == "files/synthetic-0"
        assert row.provider_file_expires_at == replacement_expiry
        assert row.provider_file_retry_at is None


def test_proxy_tail_has_explicit_source_provenance():
    from rushes.activities import effective_source_interval
    from rushes.inference import AnalysisResponse, validated_intervals

    source = Interval(start_us=0, end_us=11_491_667)
    manifest = {"source": {"duration_us": source.end_us}, "proxy": {"duration_us": 11_483_333}}
    extracted = pipeline.proxy_interval(manifest, source)
    assert extracted.end_us == 11_483_333
    assert pipeline.extraction_provenance(source, extracted) == {
        "requested_source": source.model_dump(),
        "extracted_proxy": extracted.model_dump(),
        "source_offset_us": 0,
        "trimmed_tail_us": 8334,
    }
    with pytest.raises(ValueError, match="no proxy coverage"):
        pipeline.proxy_interval(manifest, Interval(start_us=11_485_000, end_us=source.end_us))
    mapped = effective_source_interval(
        {"first_source_elapsed_us": 0, **pipeline.extraction_provenance(source, extracted)}, source
    )
    response = AnalysisResponse.model_validate(
        {
            "observations": [
                {
                    "kind": "visual_event",
                    "description": "Synthetic omitted tail",
                    "start_seconds": 11.485,
                    "end_seconds": 11.49,
                    "uncertainty": "high",
                }
            ]
        }
    )
    with pytest.raises(ValueError, match="beyond the media timeline"):
        validated_intervals(response, mapped, source.end_us)


@pytest.mark.integration
async def test_settlement_uses_64_bit_effective_coverage(authenticated):
    from rushes.activities import finish_reservation
    from rushes.credits import reserve

    _clients, ws, _other, _project, asset, _tokens = authenticated
    job_id = uuid.uuid4()
    async with tenant_session(ws) as db:
        reservation = await reserve(db, ws, f"analysis:{job_id}", 1000)
        run = AnalysisRun(
            workspace_id=ws,
            asset_id=asset,
            operation_key=str(uuid.uuid4()),
            model="synthetic",
            prompt_version="fixture",
            preprocessing_version="fixture",
            schema_version="fixture",
            transcript_version="fixture",
            sampling={"credits_per_minute": 1},
        )
        db.add(run)
        await db.flush()
        for start, requested_end, processed_end in [
            (2_400_000_000, 2_410_000_000, 2_409_000_000),
            (2_405_000_000, 2_415_000_000, 2_414_000_000),
            (2_420_000_000, 2_421_000_000, None),
        ]:
            db.add(
                AnalysisWindow(
                    workspace_id=ws,
                    asset_id=asset,
                    run_id=run.id,
                    start_us=start,
                    end_us=requested_end,
                    cache_key=str(uuid.uuid4()),
                    state="completed",
                    raw_response={
                        "chunk_mapping": {
                            "first_source_elapsed_us": start,
                            "extracted_proxy": {"end_us": processed_end},
                        }
                    }
                    if processed_end
                    else {"chunk_mapping": {"first_source_elapsed_us": start + 500_000}},
                )
            )
        await db.flush()
        await finish_reservation(db, ws, job_id, run.id)
        assert reservation.settled_milli == 250
        await reserve(db, ws, f"analysis:{job_id}", 1000, resume=True)
        await finish_reservation(db, ws, job_id, run.id)
        assert reservation.settled_milli == 250
