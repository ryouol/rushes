import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from types import SimpleNamespace
from uuid import UUID, uuid4

import psycopg
import pytest
from pydantic import SecretStr
from rushes import provider_budget, remote_compute
from rushes.config import settings
from rushes.db import tenant_session
from rushes.inference import GeminiAnalyzer
from rushes.models import AnalysisWindow, Asset, Job, Reservation, Usage
from rushes.timing import Interval
from sqlalchemy import select
from sqlalchemy.engine import make_url


@pytest.fixture
def budget_period(monkeypatch):
    period = date(3000 + uuid4().int % 6000, 1, 1)
    monkeypatch.setattr(provider_budget, "current_month", lambda: period)
    monkeypatch.setattr(settings(), "provider_monthly_allowance_microusd", 30_000)
    yield period
    url = make_url(settings().require_admin_database_url().get_secret_value()).set(
        drivername="postgresql"
    )
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        db.execute("DELETE FROM provider_spend_reservation WHERE month=%s", (period,))


@pytest.mark.integration
def test_parallel_calls_cannot_overdraw_or_reset_the_monthly_allowance(budget_period):
    def attempt(_):
        try:
            provider_budget.reserve_provider_call("modal")
            return True
        except provider_budget.ProviderBudgetError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(8))) == 3
    with pytest.raises(provider_budget.ProviderBudgetError, match="monthly AI allowance"):
        provider_budget.reserve_provider_call("modal")


@pytest.mark.integration
def test_failed_modal_call_keeps_its_reservation(budget_period, monkeypatch):
    monkeypatch.setattr(settings(), "provider_monthly_allowance_microusd", 10_000)

    def ambiguous(*args, **kwargs):
        raise TimeoutError("Synthetic unknown remote outcome")

    monkeypatch.setattr(
        remote_compute, "remote_function", lambda _: SimpleNamespace(spawn=ambiguous)
    )
    with pytest.raises(TimeoutError):
        remote_compute.RemoteEmbedder().embed(["Synthetic"])
    with pytest.raises(provider_budget.ProviderBudgetError):
        remote_compute.RemoteEmbedder().embed(["Synthetic"])


def test_empty_allowance_blocks_all_provider_boundaries_before_network(monkeypatch, tmp_path):
    monkeypatch.setattr(settings(), "provider_monthly_allowance_microusd", 0)
    monkeypatch.setattr(settings(), "gemini_api_key", SecretStr("synthetic-no-network"))

    def deny(_):
        raise provider_budget.ProviderBudgetError("Monthly allowance exhausted")

    def unexpected(*args, **kwargs):
        pytest.fail("Budget denial must prevent all provider network calls")

    from google import genai
    from rushes import inference

    monkeypatch.setattr(inference, "reserve_provider_call", deny)
    monkeypatch.setattr(remote_compute, "reserve_provider_call", deny)
    monkeypatch.setattr(remote_compute, "remote_function", unexpected)
    monkeypatch.setattr(genai, "Client", unexpected)
    interval = Interval(start_us=0, end_us=1_000_000)
    path = tmp_path / "synthetic.wav"
    path.write_bytes(b"synthetic")
    result = GeminiAnalyzer().analyze(path, interval, "")
    assert result.provider_outcome == "budget_rejected" and result.input_tokens == 0
    with pytest.raises(provider_budget.ProviderBudgetError):
        remote_compute.RemoteEmbedder().embed(["Synthetic"])
    with pytest.raises(provider_budget.ProviderBudgetError):
        remote_compute.transcribe_remote(path, interval)


def test_database_options_preserve_spaces_and_override_timeout(monkeypatch):
    monkeypatch.setattr(settings(), "provider_monthly_allowance_microusd", 10_000)
    monkeypatch.setattr(
        settings(),
        "database_url",
        SecretStr(
            "postgresql+psycopg://user:synthetic@localhost/example?connect_timeout=10&sslrootcert=%2Fpath+with+spaces%2Fca.pem"
        ),
    )

    def unavailable(dsn, **options):
        assert "?" not in dsn
        assert options == {"connect_timeout": 5, "sslrootcert": "/path with spaces/ca.pem"}
        raise psycopg.OperationalError("Synthetic unavailable database")

    monkeypatch.setattr(provider_budget.psycopg, "connect", unavailable)
    with pytest.raises(provider_budget.ProviderBudgetError, match="No provider request was sent"):
        provider_budget.reserve_provider_call("modal")


async def test_search_explains_budget_denial(monkeypatch):
    from rushes import routes_search

    def deny(_):
        raise provider_budget.ProviderBudgetError("The monthly AI allowance is used up.")

    monkeypatch.setattr(routes_search, "embedder", lambda: SimpleNamespace(embed=deny))
    vector, notice = await routes_search.query_embedding("notebook")
    assert vector is None and "monthly AI allowance" in notice and "Keyword evidence" in notice


@pytest.mark.integration
@pytest.mark.parametrize(
    "outcome", ["budget_rejected", "preparation_failed", "generation_rejected"]
)
async def test_unsent_window_remains_retryable_without_usage(
    authenticated, monkeypatch, tmp_path, outcome
):
    from datetime import timedelta

    from rushes import activities
    from rushes.inference import AnalysisResult, ProviderPreparationError
    from rushes.models import now

    _clients, ws, _other, project, asset, _tokens = authenticated
    monkeypatch.setattr(settings(), "gemini_api_key", SecretStr("synthetic-no-network"))
    monkeypatch.setattr(activities, "heartbeat", lambda *_: None)
    async with tenant_session(ws) as db:
        job = Job(
            workspace_id=ws,
            project_id=project,
            asset_id=asset,
            kind="asset",
            state="running",
            workflow_id=f"test:{uuid4()}",
        )
        db.add(job)
        await db.flush()
        job_id = job.id
    args = {"workspace_id": str(ws), "asset_id": str(asset), "job_id": str(job_id)}
    run = await activities.plan_analysis(args)
    window_id = await activities.next_window({**args, **run})
    chunk = tmp_path / "synthetic.mp4"
    chunk.write_bytes(b"never sent")
    chunk.with_suffix(".timing.json").write_text(
        json.dumps({"first_source_elapsed_us": 0, "extracted_proxy": {"end_us": 10_000_000}})
    )
    monkeypatch.setattr(activities, "prepare_chunk", lambda *_: chunk)
    expiry = now() + timedelta(hours=48)
    monkeypatch.setattr(
        activities,
        "GeminiAnalyzer",
        lambda model: SimpleNamespace(
            analyze=lambda *_: AnalysisResult(
                raw={},
                model=model,
                provider_outcome=outcome,
                validation_error="Monthly AI allowance used up",
                cleanup_pending_file="files/synthetic-pending"
                if outcome == "preparation_failed"
                else None,
                cleanup_pending_file_expires_at=expiry if outcome == "preparation_failed" else None,
            )
        ),
    )
    with pytest.raises(
        provider_budget.ProviderBudgetError
        if outcome == "budget_rejected"
        else ProviderPreparationError
    ):
        await activities.analyze_window({**args, "window_id": window_id})
    await activities.fail_job({**args, "state": "failed", "error": "Monthly AI allowance used up"})
    async with tenant_session(ws) as db:
        window = await db.get(AnalysisWindow, UUID(window_id))
        assert window.state == "pending" and window.attempts == 0
        assert await db.scalar(select(Usage.id).where(Usage.asset_id == asset)) is None
    assert await activities.next_window({**args, **run}) == window_id
    response = await _clients[0].post(f"/api/workspaces/{ws}/assets/{asset}/retry")
    assert response.status_code == 202 and response.json()["job_id"] == str(job_id)
    assert await activities.plan_analysis(args) == run
    cleaned = []
    if outcome == "preparation_failed":

        def unavailable_cleanup(_name, _expiry):
            raise TimeoutError("Synthetic failed cleanup")

        monkeypatch.setattr(activities, "delete_remote", unavailable_cleanup)
        with pytest.raises(ProviderPreparationError, match="No new analysis was sent"):
            await activities.analyze_window({**args, "window_id": window_id})
        async with tenant_session(ws) as db:
            window = await db.get(AnalysisWindow, UUID(window_id))
            assert window.state == "pending" and window.attempts == 0
            assert window.provider_file == "files/synthetic-pending"
            assert window.provider_file_expires_at == expiry
            window.provider_file_expires_at = now() - timedelta(minutes=1)

    def expired_cleanup(name, expires_at):
        from rushes.maintenance import delete_remote

        cleaned.append(name)
        delete_remote(name, expires_at)

    monkeypatch.setattr(activities, "delete_remote", expired_cleanup)
    chunk.write_bytes(b"synthetic restored allowance")
    monkeypatch.setattr(
        activities,
        "GeminiAnalyzer",
        lambda model: SimpleNamespace(
            analyze=lambda *_: AnalysisResult(
                raw={}, text='{"observations":[]}', model=model, input_tokens=12
            )
        ),
    )
    assert await activities.analyze_window({**args, "window_id": window_id}) == "completed"
    assert cleaned == (["files/synthetic-pending"] if outcome == "preparation_failed" else [])
    assert await activities.next_window({**args, **run}) is None
    await activities.finish_asset({**args, **run})
    async with tenant_session(ws) as db:
        window = await db.get(AnalysisWindow, UUID(window_id))
        assert window.attempts == 1
        assert window.provider_file is None and window.provider_file_expires_at is None
        usage = await db.scalar(select(Usage).where(Usage.asset_id == asset))
        assert usage.provider_outcome == "confirmed" and usage.input_tokens == 12
        reservation = await db.scalar(
            select(Reservation).where(Reservation.operation_key == f"analysis:{job_id}")
        )
        assert reservation.settled_milli == 167


@pytest.mark.integration
async def test_interrupted_analysis_keeps_uploaded_file_expiry(
    authenticated, monkeypatch, tmp_path
):
    from datetime import timedelta

    from rushes import activities
    from rushes.models import now

    _clients, ws, _other, project, asset, _tokens = authenticated
    monkeypatch.setattr(settings(), "gemini_api_key", SecretStr("synthetic-no-network"))
    monkeypatch.setattr(activities, "heartbeat", lambda *_: None)
    async with tenant_session(ws) as db:
        job = Job(
            workspace_id=ws,
            project_id=project,
            asset_id=asset,
            kind="asset",
            state="running",
            workflow_id=f"test:{uuid4()}",
        )
        db.add(job)
        await db.flush()
        job_id = job.id
    args = {"workspace_id": str(ws), "asset_id": str(asset), "job_id": str(job_id)}
    run = await activities.plan_analysis(args)
    window_id = await activities.next_window({**args, **run})
    chunk = tmp_path / "synthetic.mp4"
    chunk.write_bytes(b"never sent")
    chunk.with_suffix(".timing.json").write_text(
        json.dumps({"first_source_elapsed_us": 0, "extracted_proxy": {"end_us": 10_000_000}})
    )
    monkeypatch.setattr(activities, "prepare_chunk", lambda *_: chunk)
    expiry = now() + timedelta(hours=48)
    calls = []

    def interrupted(_path, _interval, _transcript, uploaded):
        calls.append(True)
        uploaded("files/synthetic-interrupted", expiry)
        raise TimeoutError("Synthetic interruption after upload checkpoint")

    monkeypatch.setattr(
        activities, "GeminiAnalyzer", lambda _: SimpleNamespace(analyze=interrupted)
    )
    window_args = {**args, "window_id": window_id}
    with pytest.raises(TimeoutError, match="Synthetic interruption"):
        await activities.analyze_window(window_args)
    async with tenant_session(ws) as db:
        window = await db.get(AnalysisWindow, UUID(window_id))
        assert window.state == "in_flight" and window.attempts == 1
        assert window.provider_file == "files/synthetic-interrupted"
        assert window.provider_file_expires_at == expiry
        assert window.provider_file_retry_at is None
    assert await activities.analyze_window(window_args) == "ambiguous"
    assert calls == [True]


@pytest.mark.integration
async def test_failed_index_can_be_retried_without_reprocessing_footage(authenticated):
    clients, ws, _other, project, asset, _tokens = authenticated
    async with tenant_session(ws) as db:
        job = Job(
            workspace_id=ws,
            project_id=project,
            asset_id=asset,
            kind="index",
            state="failed",
            workflow_id=f"index:test:{uuid4()}",
        )
        db.add(job)
        await db.flush()
        job_id = job.id
        before = (await db.get(Asset, asset)).status
    # A later successful note index must not hide this independently failed subset.
    async with tenant_session(ws) as db:
        db.add(
            Job(
                workspace_id=ws,
                project_id=project,
                asset_id=asset,
                kind="index",
                state="completed",
                workflow_id=f"index:newer:{uuid4()}",
            )
        )
    base = f"/api/workspaces/{ws}/assets/{asset}"
    assert (await clients[0].get(base)).json()["can_retry"]
    assert (await clients[1].post(base + "/retry")).status_code == 403
    response = await clients[0].post(base + "/retry")
    assert response.status_code == 202
    assert (await clients[0].post(base + "/retry")).status_code == 409
    async with tenant_session(ws) as db:
        job = await db.get(Job, job_id)
        assert job.state == "queued" and job.workflow_id.startswith("index:")
        assert (await db.get(Asset, asset)).status == before
