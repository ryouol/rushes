import csv
import json
import uuid
from datetime import UTC, datetime

import pytest
from rushes import activities, exports, routes_search
from rushes.config import settings
from rushes.db import tenant_session
from rushes.models import AnalysisRun, Embedding, Export, Job, MediaTimeline, Observation
from sqlalchemy import select

pytestmark = pytest.mark.integration


@pytest.fixture
async def evidence(authenticated):
    clients, workspace, _, project, asset, _ = authenticated
    async with tenant_session(workspace) as db:
        timeline = await db.scalar(select(MediaTimeline).where(MediaTimeline.asset_id == asset))
        timeline.details = {**timeline.details, "time_base": "1/24000"}
        runs = []
        for day in (1, 2):
            run = AnalysisRun(
                workspace_id=workspace,
                asset_id=asset,
                operation_key=str(uuid.uuid4()),
                model="synthetic",
                prompt_version="test",
                preprocessing_version="test",
                schema_version="observations-v2",
                transcript_version="test",
                sampling={},
                status="ready",
                created_at=datetime(2026, 1, day, tzinfo=UTC),
            )
            db.add(run)
            await db.flush()
            runs.append(run.id)
        current, stale = set(), set()
        # More stale matches than either retrieval candidate limit: filter before limiting.
        rows = [
            (runs[0], "unreviewed", "visual_event", f"Obsolete zebra finding {i}")
            for i in range(65)
        ]
        rows += [
            (runs[1], "unreviewed", "visual_event", "Current ocean finding"),
            (runs[0], "corrected", "visual_event", "Human corrected finding"),
            (None, "unreviewed", "note", "Human note finding"),
            (None, "unreviewed", "speech", "Spoken transcript finding"),
        ]
        for index, (run, review, kind, description) in enumerate(rows):
            row = Observation(
                workspace_id=workspace,
                asset_id=asset,
                timeline_id=timeline.id,
                run_id=run,
                operation_key=str(uuid.uuid4()),
                kind=kind,
                start_us=index * 10_000,
                end_us=(index + 1) * 10_000,
                proposed_start_us=index * 10_000,
                proposed_end_us=(index + 1) * 10_000,
                description=description,
                producer="synthetic",
                model="synthetic",
                prompt_version="test",
                preprocessing_version="test",
                review_status=review,
            )
            db.add(row)
            await db.flush()
            (stale if index < 65 else current).add(str(row.id))
            db.add(
                Embedding(
                    workspace_id=workspace,
                    observation_id=row.id,
                    model=settings().embedding_model,
                    dimension=384,
                    text_hash=str(uuid.uuid4()),
                    vector=[0.01] * 384,
                )
            )
    return clients, workspace, project, asset, current, stale, runs


@pytest.mark.parametrize("semantic", [False, True])
async def test_search_filters_old_runs_before_candidate_limits(evidence, monkeypatch, semantic):
    clients, workspace, project, _, current, _, _ = evidence

    async def vector(*args):
        return [0.01] * 384, None

    async def relevance(workspace, query, texts):
        return [1.0] * len(texts)

    monkeypatch.setattr(routes_search, "query_embedding", vector)
    monkeypatch.setattr(routes_search, "relevance_scores", relevance)
    response = await clients[0].get(
        f"/api/workspaces/{workspace}/projects/{project}/search",
        params={"q": "no_keyword_match" if semantic else "finding", "semantic": semantic},
    )
    assert response.status_code == 200
    found = {e["observation_id"] for r in response.json()["results"] for e in r["evidence"]}
    assert found == current


async def test_worklog_history_and_context_preserve_but_label_old_evidence(evidence):
    clients, workspace, _, asset, current, stale, _ = evidence
    url = f"/api/workspaces/{workspace}/assets/{asset}/observations"
    response = await clients[0].get(url, params={"limit": 2, "near_us": 0})
    assert response.status_code == 200
    assert response.json()["total"] == 4
    assert {r["id"] for r in response.json()["items"]} <= current
    response = await clients[0].get(url, params={"include_history": True})
    rows = response.json()["items"]
    assert {r["id"] for r in rows if r["superseded"]} == stale
    assert {r["id"] for r in rows if not r["superseded"]} == current
    old = sorted(stale)[0]
    response = await clients[0].get(f"/api/workspaces/{workspace}/observations/{old}/context")
    assert response.status_code == 200
    assert response.json()["citation"]["superseded"] is True
    rows = response.json()["evidence"]
    assert rows[0]["id"] == old and rows[0]["superseded"] is True
    assert {r["id"] for r in rows[1:]} == current
    assert all(not r["superseded"] for r in rows[1:])
    assert (await clients[2].get(url, params={"include_history": True})).status_code == 404


@pytest.mark.parametrize("state", ["running", "partial", "failed"])
async def test_new_run_does_not_resurrect_old_machine_evidence(evidence, state):
    clients, workspace, _, asset, current, _, runs = evidence
    async with tenant_session(workspace) as db:
        latest = await db.get(AnalysisRun, runs[-1])
        latest.status = state
        latest.created_at = datetime(2026, 1, 3, tzinfo=UTC)
        # The newer attempt has no observations yet; human and transcript evidence remain.
        for row in await db.scalars(select(Observation).where(Observation.run_id == latest.id)):
            row.run_id = runs[0]
            current.remove(str(row.id))
    response = await clients[0].get(f"/api/workspaces/{workspace}/assets/{asset}/observations")
    assert {r["id"] for r in response.json()["items"]} == current


@pytest.mark.parametrize("kind", ["json", "csv"])
async def test_worklog_exports_use_current_evidence(evidence, monkeypatch, tmp_path, kind):
    _, workspace, project, _, current, _, _ = evidence
    monkeypatch.setattr(settings(), "output_root", tmp_path / "outputs")
    monkeypatch.setattr(settings(), "min_free_bytes", 0)
    monkeypatch.setattr(activities, "heartbeat", lambda *_: None)
    monkeypatch.setattr(exports, "heartbeat", lambda *_: None)
    async with tenant_session(workspace) as db:
        job = Job(
            workspace_id=workspace,
            project_id=project,
            kind="export",
            workflow_id=str(uuid.uuid4()),
            state="running",
        )
        db.add(job)
        await db.flush()
        export = Export(
            workspace_id=workspace,
            project_id=project,
            job_id=job.id,
            kind=kind,
            name="Current evidence",
            plan={"entries": [], "estimated_bytes": 0},
        )
        db.add(export)
        await db.flush()
        export_id, job_id = export.id, job.id
    await exports.render_export({"workspace_id": str(workspace), "job_id": str(job_id)})
    target = exports.export_folder(workspace, export_id) / f"worklog.{kind}"
    if kind == "json":
        rows = json.loads(target.read_text())["observations"]
    else:
        with target.open(newline="") as file:
            rows = list(csv.DictReader(file))
    assert {r["observation_id"] for r in rows} == current
