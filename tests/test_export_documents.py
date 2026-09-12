import asyncio
import csv
import json
import threading
import uuid

import pytest
from rushes import activities, export_documents, exports
from rushes.config import settings
from rushes.db import tenant_session
from rushes.models import Export, Job, MediaTimeline, Observation
from sqlalchemy import select


@pytest.mark.integration
@pytest.mark.parametrize("kind", ["json", "csv"])
async def test_worklog_batches_preserve_rows_and_leave_the_api_responsive(
    authenticated, monkeypatch, tmp_path, kind
):
    clients, workspace, _other, project, asset, _tokens = authenticated
    monkeypatch.setattr(settings(), "output_root", tmp_path / "outputs")
    monkeypatch.setattr(settings(), "min_free_bytes", 0)
    monkeypatch.setattr(activities, "heartbeat", lambda *_: None)
    monkeypatch.setattr(exports, "heartbeat", lambda *_: None)
    async with tenant_session(workspace) as db:
        timeline = await db.scalar(select(MediaTimeline).where(MediaTimeline.asset_id == asset))
        timeline.details = {"duration_us": 10_000_000, "time_base": "1/24000"}
        for index in range(401):
            db.add(
                Observation(
                    workspace_id=workspace,
                    asset_id=asset,
                    timeline_id=timeline.id,
                    operation_key=f"test:{uuid.uuid4()}",
                    kind="speech",
                    start_us=index * 10_000,
                    end_us=(index + 1) * 10_000,
                    proposed_start_us=index * 10_000,
                    proposed_end_us=(index + 1) * 10_000,
                    description=f'=Synthetic,{index}\nquoted "text"',
                    producer="test",
                    model="test",
                    prompt_version="test",
                    preprocessing_version="test",
                )
            )
        job = Job(
            workspace_id=workspace,
            project_id=project,
            kind="export",
            workflow_id=f"test:{uuid.uuid4()}",
            state="running",
        )
        db.add(job)
        await db.flush()
        export = Export(
            workspace_id=workspace,
            project_id=project,
            job_id=job.id,
            kind=kind,
            name="Synthetic worklog",
            plan={"entries": [], "estimated_bytes": 0},
        )
        db.add(export)
        await db.flush()
        export_id, job_id = export.id, job.id

    entered, release = threading.Event(), threading.Event()
    original = export_documents.require_space

    def slow_disk(*args):
        entered.set()
        assert release.wait(3), "Export blocked the event loop while waiting for disk"
        return original(*args)

    monkeypatch.setattr(export_documents, "require_space", slow_disk)
    task = asyncio.create_task(
        exports.render_export({"workspace_id": str(workspace), "job_id": str(job_id)})
    )
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        response = await asyncio.wait_for(clients[0].get("/api/health"), 1)
        assert response.status_code == 200
    finally:
        release.set()
        await asyncio.wait_for(task, 5)

    target = exports.export_folder(workspace, export_id) / f"worklog.{kind}"
    if kind == "json":
        document = json.loads(target.read_text())
        assert document["schema"] == "rushes-worklog-v1"
        rows = document["observations"]
    else:
        with target.open(newline="") as file:
            rows = list(csv.DictReader(file))
    assert len(rows) == 401
    for index, row in enumerate(rows):
        assert int(row["start_us"]) == index * 10_000
        assert (
            row["description"]
            == ("'" if kind == "csv" else "") + f'=Synthetic,{index}\nquoted "text"'
        )
        assert row["time_base"] == "1/24000"
        assert row["asset_id"] == str(asset)
    async with tenant_session(workspace) as db:
        assert (await db.get(Job, job_id)).state == "completed"
        assert (await db.get(Export, export_id)).provenance["outputs"][0][
            "bytes"
        ] == target.stat().st_size
