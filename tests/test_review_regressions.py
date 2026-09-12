import json
import os
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import SecretStr
from rushes import activities, exports, routes_search
from rushes.config import settings
from rushes.db import tenant_session
from rushes.inference import AnalysisResult
from rushes.models import (
    AnalysisRun,
    AnalysisWindow,
    Job,
    LedgerEntry,
    MediaTimeline,
    Observation,
    Usage,
    Workspace,
)
from rushes.storage import StorageError, fingerprint
from sqlalchemy import select, text


def test_many_selections_share_source_verification_and_reuse_outputs(tmp_path, monkeypatch):
    source = tmp_path / "camera-original.bin"
    source.write_bytes(b"synthetic-source" * 100)
    with source.open("rb") as file:
        expected = fingerprint(file)
    entries = [
        {
            "source_root": str(tmp_path),
            "relative_path": source.name,
            "fingerprint": expected,
            "filename": f"select-{i}.bin",
            "mode": "copy",
            "estimated_bytes": source.stat().st_size,
            "asset_id": "synthetic",
            "source_name": source.name,
        }
        for i in range(5)
    ]
    reads = []

    def count_reads(file):
        if file.name == source.name or isinstance(file.name, int):
            reads.append(file.name)
        return fingerprint(file)

    monkeypatch.setattr(exports, "fingerprint", count_reads)
    folder = tmp_path / "outputs"
    key, group = next(iter(exports.source_groups(entries)))
    first = exports.write_media_group(key, group, folder)
    mtimes = [(folder / row["output"]).stat().st_mtime_ns for row in first]
    assert len(reads) == 2
    assert exports.write_media_group(key, group, folder) == first
    assert mtimes == [(folder / row["output"]).stat().st_mtime_ns for row in first]
    assert len(reads) == 4
    assert all((folder / row["output"]).read_bytes() == source.read_bytes() for row in first)
    source.write_bytes(b"changed")
    with pytest.raises(StorageError, match="Source contents changed"):
        exports.write_media_group(key, group, folder)


@pytest.mark.integration
async def test_sql_error_in_semantic_index_keeps_keyword_evidence(authenticated, monkeypatch):
    clients, ws, _other, project, asset, _tokens = authenticated
    note = await clients[0].post(
        f"/api/workspaces/{ws}/assets/{asset}/observations",
        json={
            "description": "A red notebook",
            "start_us": 0,
            "end_us": 1_000_000,
            "request_id": str(uuid.uuid4()),
        },
    )
    assert note.status_code == 201
    async with tenant_session(ws) as db:
        scalars = db.scalars
        calls = 0

        async def fail_vector_query(statement, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                # Produce a real aborted PostgreSQL subtransaction, not a Python mock error.
                await db.execute(text("SELECT 1 / 0"))
            return await scalars(statement, *args, **kwargs)

        monkeypatch.setattr(db, "scalars", fail_vector_query)
        results, notice = await routes_search.search_evidence(
            db, SimpleNamespace(workspace_id=ws), project, "notebook", 20, [0.1, 0.2], None
        )
        assert results[0]["evidence"][0]["observation_id"] == uuid.UUID(note.json()["id"])
        assert "keyword evidence" in notice
        assert await db.scalar(text("SELECT 1")) == 1


@pytest.mark.integration
async def test_analysis_uses_frozen_transcript_and_canceled_requests_are_ambiguous(
    authenticated, monkeypatch, tmp_path
):
    clients, ws, _other, project, asset, _tokens = authenticated
    note = await clients[0].post(
        f"/api/workspaces/{ws}/assets/{asset}/observations",
        json={
            "description": "Original spoken words",
            "start_us": 0,
            "end_us": 1_000_000,
            "request_id": str(uuid.uuid4()),
        },
    )
    note_id = uuid.UUID(note.json()["id"])
    async with tenant_session(ws) as db:
        original = await db.get(Observation, note_id)
        original.kind, original.producer = "speech", "faster-whisper"
        job = Job(
            workspace_id=ws,
            project_id=project,
            asset_id=asset,
            kind="asset",
            workflow_id=f"test:{uuid.uuid4()}",
            state="running",
        )
        db.add(job)
        await db.flush()
        job_id = job.id
    config = settings().model_copy(update={"gemini_api_key": SecretStr("test-only-no-network")})
    monkeypatch.setattr(activities, "settings", lambda: config)
    monkeypatch.setattr(activities, "heartbeat", lambda *_: None)
    args = {"workspace_id": str(ws), "asset_id": str(asset), "job_id": str(job_id)}
    run_id = (await activities.plan_analysis(args))["run_id"]
    async with tenant_session(ws) as db:
        row = await db.get(Observation, note_id)
        row.description, row.version = "Edited after planning", 2
        window = await db.scalar(
            select(AnalysisWindow).where(AnalysisWindow.run_id == uuid.UUID(run_id))
        )
        window_id, cache_key = window.id, window.cache_key
    assert (await activities.plan_analysis(args))["run_id"] == run_id
    chunk = tmp_path / "synthetic-provider-interface.mp4"
    chunk.write_bytes(b"isolated interface fixture; never sent to provider")
    chunk.with_suffix(".timing.json").write_text(
        json.dumps(
            {"first_source_elapsed_us": 0, "extracted_proxy": {"start_us": 0, "end_us": 9_000_000}}
        )
    )
    monkeypatch.setattr(activities, "prepare_chunk", lambda *_: chunk)
    calls = []

    class SyntheticAnalyzer:
        def __init__(self, model):
            self.model = model

        def analyze(self, _chunk, _window, transcript, _uploaded):
            assert _window.end_us == 9_000_000
            calls.append(transcript)
            return AnalysisResult(
                text=json.dumps(
                    {
                        "observations": [
                            {
                                "kind": "visual_event",
                                "description": "Synthetic visible notebook",
                                "start_seconds": 0,
                                "end_seconds": 1,
                                "uncertainty": "high",
                            }
                        ]
                    }
                ),
                raw={"fixture": "received"},
                model=self.model,
                input_tokens=42,
            )

    monkeypatch.setattr(activities, "GeminiAnalyzer", SyntheticAnalyzer)
    assert await activities.analyze_window({**args, "window_id": str(window_id)}) == "completed"
    assert calls == ["Original spoken words"] and not chunk.exists()
    async with tenant_session(ws) as db:
        window = await db.get(AnalysisWindow, window_id)
        assert window.cache_key == cache_key
        assert window.input_snapshot["observation_versions"][0]["version"] == 1
        result = await db.scalar(select(Observation).where(Observation.window_id == window.id))
        assert result.description == "Synthetic visible notebook"
        assert result.start_us == 0 and result.end_us == 1_000_000
        assert window.raw_response["provider"] == {"fixture": "received"}
        usage = await db.scalar(select(Usage).where(Usage.operation_key == f"analysis:{window_id}"))
        assert usage.duration_us == 9_000_000
        await activities.finish_reservation(db, ws, job_id, uuid.UUID(run_id))
        from rushes.models import Reservation

        reservation = await db.scalar(
            select(Reservation).where(Reservation.operation_key == f"analysis:{job_id}")
        )
        assert reservation.settled_milli == 150
        uncertain = AnalysisWindow(
            workspace_id=ws,
            asset_id=asset,
            run_id=uuid.UUID(run_id),
            start_us=2_000_000,
            end_us=3_000_000,
            cache_key=str(uuid.uuid4()),
            state="in_flight",
            attempts=1,
        )
        db.add(uncertain)
        await db.flush()
        uncertain_id = uncertain.id
    for _ in range(2):
        await activities.fail_job({**args, "state": "canceled", "error": "Synthetic cancellation"})
    async with tenant_session(ws) as db:
        assert (await db.get(AnalysisWindow, uncertain_id)).state == "ambiguous"
        rows = list(
            await db.scalars(
                select(Usage).where(Usage.operation_key == f"ambiguous:{uncertain_id}")
            )
        )
        assert len(rows) == 1 and rows[0].model == config.gemini_model
        assert (await db.get(AnalysisRun, uuid.UUID(run_id))).status == "canceled"


def test_cleanup_preserves_completed_outputs_with_partial_in_source_name(tmp_path):
    from rushes.maintenance import clean_old_units

    temporary = tmp_path / f".preview.{uuid.uuid4().hex}.partial.mp4"
    final = tmp_path / "0001-camera.partial.mp4"
    receipt = tmp_path / "0001-camera.partial.mp4.receipt.json"
    tricky = tmp_path / f"0001-camera.{uuid.uuid4().hex}.partial.mp4"
    for path in (temporary, final, receipt, tricky):
        path.write_bytes(b"synthetic")
        os.utime(path, (time.time() - 90000, time.time() - 90000))
    clean_old_units(iter((temporary, final, receipt, tricky)))
    assert not temporary.exists()
    assert final.exists() and receipt.exists() and tricky.exists()


@pytest.mark.integration
async def test_resumed_reservation_only_charges_new_confirmed_coverage(account_workspace):
    from rushes.credits import reserve, settle

    ws, operation = account_workspace, f"test:{uuid.uuid4()}"
    async with tenant_session(ws) as db:
        await reserve(db, ws, operation, 800)
        await settle(db, ws, operation, 300)
    async with tenant_session(ws) as db:
        await reserve(db, ws, operation, 800, resume=True)
        await reserve(db, ws, operation, 800, resume=True)
        assert (await db.get(Workspace, ws)).balance_milli == 200
        await settle(db, ws, operation, 600)
        await settle(db, ws, operation, 600)
    async with tenant_session(ws) as db:
        assert (await db.get(Workspace, ws)).balance_milli == 400
        entries = list(await db.scalars(select(LedgerEntry).where(LedgerEntry.workspace_id == ws)))
        assert len(entries) == 4 and sum(row.delta_milli for row in entries) == -600


@pytest.mark.integration
async def test_long_worklog_filters_anchor_and_context(authenticated):
    clients, ws, _other, _project, asset, _tokens = authenticated
    async with tenant_session(ws) as db:
        timeline = await db.scalar(select(MediaTimeline).where(MediaTimeline.asset_id == asset))
        for i in range(140):
            row = Observation(
                workspace_id=ws,
                asset_id=asset,
                timeline_id=timeline.id,
                operation_key=f"test:{uuid.uuid4()}",
                kind="speech" if i >= 130 else "other",
                start_us=i * 50000,
                end_us=(i + 1) * 50000,
                proposed_start_us=i * 50000,
                proposed_end_us=(i + 1) * 50000,
                description=f"Synthetic observation {i}",
                attributes={},
                evidence=[],
                producer="test",
                model="test",
                prompt_version="test",
                preprocessing_version="test",
                uncertainty="high",
            )
            db.add(row)
            if i == 135:
                anchor = row
        await db.flush()
        anchor_id = anchor.id
    base = f"/api/workspaces/{ws}"
    late = (await clients[0].get(f"{base}/assets/{asset}/observations?near_us=6750000")).json()
    assert late["offset"] == 100 and any(row["id"] == str(anchor_id) for row in late["items"])
    boundary = (await clients[0].get(f"{base}/assets/{asset}/observations?near_us=4975000")).json()
    assert boundary["offset"] == 0
    assert any(row["description"] == "Synthetic observation 99" for row in boundary["items"])
    speech = (await clients[0].get(f"{base}/assets/{asset}/observations?kind=speech")).json()
    assert speech["total"] == 10 and len(speech["items"]) == 10
    context = (await clients[0].get(f"{base}/observations/{anchor_id}/context")).json()
    assert len(context["evidence"]) <= 12 and context["evidence"][0]["id"] == str(anchor_id)


@pytest.mark.integration
async def test_batch_children_do_not_starve_standalone_dispatch(authenticated, monkeypatch):
    from rushes import worker

    _clients, ws, _other, project, asset, _tokens = authenticated
    batch = str(uuid.uuid4())
    async with tenant_session(ws) as db:
        for _ in range(50):
            db.add(
                Job(
                    workspace_id=ws,
                    project_id=project,
                    asset_id=asset,
                    kind="asset",
                    workflow_id=f"test:{uuid.uuid4()}",
                    payload={"batch_id": batch},
                )
            )
        independent = Job(
            workspace_id=ws, project_id=project, kind="export", workflow_id=f"test:{uuid.uuid4()}"
        )
        db.add(independent)
        await db.flush()
        expected = independent.workflow_id
    started = []

    class FakeTemporal:
        async def start_workflow(self, _run, _args, **kwargs):
            started.append(kwargs["id"])

    await worker.dispatch_workspace(FakeTemporal(), ws)
    assert expected in started


@pytest.mark.integration
async def test_received_invalid_response_retains_usage_without_repeat(authenticated, monkeypatch):
    clients, ws, _other, _project, asset, _tokens = authenticated
    async with tenant_session(ws) as db:
        run = AnalysisRun(
            workspace_id=ws,
            asset_id=asset,
            operation_key=f"test:{uuid.uuid4()}",
            model="synthetic",
            prompt_version="test",
            preprocessing_version="test",
            schema_version="test",
            transcript_version="test",
            sampling={},
        )
        db.add(run)
        await db.flush()
        row = AnalysisWindow(
            workspace_id=ws,
            asset_id=asset,
            run_id=run.id,
            start_us=0,
            end_us=1000000,
            cache_key=str(uuid.uuid4()),
            state="received",
            attempts=1,
            raw_response={
                "provider": {"received": "invalid-json"},
                "envelope": {"text": "invalid json", "model": "synthetic", "input_tokens": 123},
                "chunk_mapping": {"first_source_elapsed_us": 0},
            },
        )
        db.add(row)
        await db.flush()
        id = row.id
        db.add(
            Usage(
                workspace_id=ws,
                asset_id=asset,
                operation_key=f"analysis:{id}",
                kind="analysis",
                model="synthetic",
                input_tokens=123,
                provider_outcome="received",
            )
        )
    args = {"workspace_id": str(ws), "window_id": str(id)}
    assert await activities.apply_received_response(args) == "failed"
    assert await activities.apply_received_response(args) == "failed"
    async with tenant_session(ws) as db:
        assert (await db.get(AnalysisWindow, id)).raw_response["provider"] == {
            "received": "invalid-json"
        }
        usage = await db.scalar(select(Usage).where(Usage.operation_key == f"analysis:{id}"))
        assert usage.input_tokens == 123 and usage.provider_outcome == "invalid_response"


@pytest.mark.integration
@pytest.mark.parametrize("kind", ["copies", "selections_json", "selections_csv"])
async def test_export_uses_relinked_source_preserves_paths_and_replays_completion(
    authenticated, monkeypatch, tmp_path, kind
):
    from rushes.models import Asset, Export

    _clients, ws, _other, project, asset_id, _tokens = authenticated
    monkeypatch.setattr(activities, "heartbeat", lambda *_: None)
    monkeypatch.setattr(exports, "heartbeat", lambda *_: None)
    monkeypatch.setattr(settings(), "output_root", tmp_path / "outputs")
    async with tenant_session(ws) as db:
        asset = await db.get(Asset, asset_id)
        source_path = Path(asset.source_root) / asset.relative_path
        with source_path.open("rb") as file:
            asset.fingerprint = fingerprint(file)
        asset.import_relative_path = "Shoot A/Camera 2/Original name.mp4"
        entry = {
            "asset_id": str(asset_id),
            "source_root": "/missing-old-source",
            "relative_path": "old.mp4",
            "fingerprint": asset.fingerprint,
            "source_name": asset.name,
            "filename": "0001-Synthetic.mp4",
            "estimated_bytes": 10,
            "mode": "copy",
            "start_us": 0,
            "end_us": 1000000,
            "timeline": {"time_base": "1/24000"},
        }
        job = Job(
            workspace_id=ws,
            project_id=project,
            kind="export",
            workflow_id=f"test:{uuid.uuid4()}",
            state="running",
        )
        db.add(job)
        await db.flush()
        output = Export(
            workspace_id=ws,
            project_id=project,
            job_id=job.id,
            kind=kind,
            name="Synthetic export",
            plan={"entries": [entry], "estimated_bytes": 10},
        )
        db.add(output)
        await db.flush()
        export_id, job_id = output.id, job.id
    args = {"workspace_id": str(ws), "job_id": str(job_id)}
    first = await exports.render_export(args)
    assert await exports.render_export(args) == first
    async with tenant_session(ws) as db:
        assert (await db.get(Job, job_id)).state == "completed"
        output = await db.get(Export, export_id)
        path = exports.export_folder(ws, export_id) / output.provenance["outputs"][0]["output"]
        if kind == "copies":
            assert path.read_bytes() == source_path.read_bytes()
        else:
            assert "Shoot A/Camera 2/Original name.mp4" in path.read_text()
        rows = list(
            await db.scalars(select(Usage).where(Usage.operation_key == f"export:{export_id}"))
        )
        assert len(rows) == 1


def test_source_root_removal_revokes_indexed_access(tmp_path, monkeypatch):
    from rushes.storage import authorized_source_root

    ws, asset = uuid.uuid4(), uuid.uuid4()
    monkeypatch.setattr(settings(), "source_roots", [tmp_path])
    assert authorized_source_root(tmp_path, ws, asset) == tmp_path
    monkeypatch.setattr(settings(), "source_roots", [])
    with pytest.raises(StorageError, match="no longer configured"):
        authorized_source_root(tmp_path, ws, asset)
    uploaded = settings().storage_root / "uploads" / str(ws) / str(asset)
    assert authorized_source_root(uploaded, ws, asset) == uploaded
    with pytest.raises(StorageError):
        authorized_source_root(uploaded, uuid.uuid4(), asset)


@pytest.mark.parametrize("input_tokens", [10001, 100])
def test_model_budget_and_measured_output_tokens(tmp_path, monkeypatch, input_tokens):
    from google import genai
    from rushes import inference
    from rushes.inference import GeminiAnalyzer, bounded_transcript

    monkeypatch.setattr(settings(), "gemini_api_key", SecretStr("test-only-no-network"))
    monkeypatch.setattr(inference, "reserve_provider_call", lambda _: None)
    events = []

    class FakeClient:
        def __init__(self, **_kwargs):
            self.files = SimpleNamespace(
                upload=self.upload, delete=lambda **kw: events.append("deleted")
            )
            self.models = SimpleNamespace(count_tokens=self.count, generate_content=self.generate)

        def upload(self, **_kwargs):
            return SimpleNamespace(
                name="files/synthetic",
                expiration_time=None,
                uri="https://example.invalid/synthetic",
                state=SimpleNamespace(name="ACTIVE"),
            )

        def count(self, **_kwargs):
            return SimpleNamespace(
                total_tokens=input_tokens, model_dump=lambda **kw: {"total_tokens": input_tokens}
            )

        def generate(self, **kwargs):
            assert input_tokens <= 10000, "Over-budget input must never be analyzed"
            assert kwargs["config"].max_output_tokens == 4096
            assert kwargs["config"].thinking_config.thinking_level == "MINIMAL"
            return SimpleNamespace(
                text='{"observations": []}',
                model_dump=lambda **kw: {"synthetic": True},
                usage_metadata=SimpleNamespace(
                    prompt_token_count=input_tokens,
                    candidates_token_count=17,
                    thoughts_token_count=100,
                ),
            )

        def close(self):
            events.append("closed")

    monkeypatch.setattr(genai, "Client", FakeClient)
    from rushes.timing import Interval

    result = GeminiAnalyzer().analyze(
        tmp_path / "unused.mp4", Interval(start_us=0, end_us=1000000), "fixture"
    )
    if input_tokens > 10000:
        assert result.provider_outcome == "input_rejected" and result.input_tokens == 0
    else:
        assert result.provider_outcome == "received"
        assert result.input_tokens == 100 and result.output_tokens == 117
    assert events == ["deleted", "closed"]
    escaped = bounded_transcript('\x00\\"' * 10000)
    assert len(json.dumps(escaped, ensure_ascii=False).encode()) <= 8000


@pytest.mark.integration
async def test_cancel_between_stage_and_provider_start_prevents_request(authenticated, monkeypatch):
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
        id = job.id
    original_stage = activities.stage

    async def cancel_after_stage(args, *rest):
        await original_stage(args, *rest)
        async with tenant_session(ws) as db:
            job = await db.scalar(select(Job).where(Job.id == id).with_for_update())
            job.state = "cancel_requested"

    monkeypatch.setattr(activities, "stage", cancel_after_stage)
    monkeypatch.setattr(activities, "heartbeat", lambda *_: None)
    args = {
        "workspace_id": str(ws),
        "asset_id": str(asset),
        "job_id": str(id),
        "window_id": str(uuid.uuid4()),
    }
    import asyncio

    with pytest.raises(asyncio.CancelledError):
        await activities.analyze_window(args)
    async with tenant_session(ws) as db:
        assert (await db.get(Job, id)).state == "cancel_requested"


@pytest.mark.integration
async def test_received_checkpoint_survives_failure_and_resumes_without_provider(
    authenticated, monkeypatch
):
    from rushes.credits import reserve
    from rushes.inference import PREPROCESSING_VERSION, PROMPT_VERSION, SCHEMA_VERSION
    from rushes.models import Reservation

    clients, ws, _other, project, asset, _tokens = authenticated
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
        id = job.id
        operation = f"analysis:{id}"
        await reserve(db, ws, operation, 500)
        run = AnalysisRun(
            workspace_id=ws,
            asset_id=asset,
            operation_key=operation,
            model="synthetic",
            prompt_version=PROMPT_VERSION,
            preprocessing_version=PREPROCESSING_VERSION,
            schema_version=SCHEMA_VERSION,
            transcript_version="test",
            sampling={"credits_per_minute": 1},
        )
        db.add(run)
        await db.flush()
        run_id = run.id
        window = AnalysisWindow(
            workspace_id=ws,
            asset_id=asset,
            run_id=run.id,
            start_us=0,
            end_us=1000000,
            state="received",
            cache_key=str(uuid.uuid4()),
            attempts=1,
            raw_response={
                "provider": {"fixture": "valid response"},
                "envelope": {"text": '{"observations":[]}', "model": "synthetic"},
                "chunk_mapping": {"first_source_elapsed_us": 0},
            },
        )
        db.add(window)
        await db.flush()
        window_id = window.id
        db.add(
            Usage(
                workspace_id=ws,
                asset_id=asset,
                operation_key=f"analysis:{window.id}",
                kind="analysis",
                model="synthetic",
                provider_outcome="received",
            )
        )
    args = {
        "workspace_id": str(ws),
        "asset_id": str(asset),
        "job_id": str(id),
        "run_id": str(run_id),
        "window_id": str(window_id),
    }
    await activities.fail_job(
        {**args, "state": "failed", "error": "Synthetic transient persistence failure"}
    )
    async with tenant_session(ws) as db:
        assert (await db.get(AnalysisWindow, window_id)).state == "received"
        assert (await db.get(Workspace, ws)).balance_milli == 1000
    response = await clients[0].post(f"/api/workspaces/{ws}/assets/{asset}/retry")
    assert response.status_code == 202
    monkeypatch.setattr(activities, "heartbeat", lambda *_: None)
    monkeypatch.setattr(settings(), "gemini_api_key", SecretStr("test-only-no-network"))
    assert (await activities.plan_analysis(args))["run_id"] == str(run_id)
    assert await activities.analyze_window(args) == "completed"
    await activities.finish_asset(args)
    async with tenant_session(ws) as db:
        reservation = await db.scalar(
            select(Reservation).where(Reservation.operation_key == operation)
        )
        assert reservation.settled_milli == 17
        assert (await db.get(Workspace, ws)).balance_milli == 983


@pytest.mark.integration
async def test_missing_workflow_cancellation_does_not_block_next_job(authenticated):
    from rushes import worker
    from temporalio.service import RPCError, RPCStatusCode

    _clients, ws, _other, project, asset, _tokens = authenticated
    async with tenant_session(ws) as db:
        canceled = Job(
            workspace_id=ws,
            project_id=project,
            asset_id=asset,
            kind="asset",
            state="cancel_requested",
            workflow_id=f"test:{uuid.uuid4()}",
        )
        next_job = Job(
            workspace_id=ws, project_id=project, kind="export", workflow_id=f"test:{uuid.uuid4()}"
        )
        db.add_all([canceled, next_job])
        await db.flush()
        canceled_id, expected = canceled.id, next_job.workflow_id
    started = []

    class MissingWorkflow:
        def get_workflow_handle(self, _id):
            return self

        async def cancel(self):
            raise RPCError("Synthetic missing workflow", RPCStatusCode.NOT_FOUND, b"")

        async def start_workflow(self, _run, _args, **kwargs):
            started.append(kwargs["id"])

    await worker.dispatch_workspace(MissingWorkflow(), ws)
    assert expected in started
    async with tenant_session(ws) as db:
        assert (await db.get(Job, canceled_id)).state == "canceled"
