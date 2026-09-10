"""Opt-in real Temporal integration: RUSHES_TEST_TEMPORAL=1 uv run pytest tests/test_temporal.py."""

import asyncio
import os
import shutil
import tempfile
import time
from pathlib import Path

import pytest
from rushes.config import settings

pytestmark = pytest.mark.skipif(
    os.environ.get("RUSHES_TEST_TEMPORAL") != "1",
    reason="Requires a running local Temporal server and matching worker",
)


async def test_selected_root_batch_recovers_files_independently(
    authenticated, tmp_path, monkeypatch
):
    clients, ws, _other, project, _asset, _tokens = authenticated
    roots = settings().source_roots
    if not roots:
        pytest.skip("Configure the same explicit synthetic source root for API and worker first")
    allowed = roots[0]
    root = Path(tempfile.mkdtemp(prefix="SYNTHETIC-batch-", dir=allowed))
    source = root / "SYNTHETIC-valid.mp4"
    shutil.copyfile(".local/fixtures/SYNTHETIC-red-blue-speech.mp4", source)
    (root / "SYNTHETIC-corrupt.mp4").write_bytes(b"Intentionally corrupt video")
    base = f"/api/workspaces/{ws}"
    response = await clients[0].post(
        f"{base}/projects/{project}/index",
        json={
            "root": 0,
            "paths": [
                str(source.relative_to(allowed)),
                str((root / "SYNTHETIC-corrupt.mp4").relative_to(allowed)),
            ],
        },
    )
    assert response.status_code == 202, response.text
    body = response.json()
    ids = [row["asset_id"] for row in body["files"]]
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        jobs = (await clients[0].get(f"{base}/jobs")).json()
        batch = next(row for row in jobs if row["id"] == body["batch_job_id"])
        if batch["state"] in {"completed", "failed"}:
            break
        await asyncio.sleep(0.5)
    assert batch["state"] == "completed", jobs
    states = [(await clients[0].get(f"{base}/assets/{id}")).json()["status"] for id in ids]
    assert states == ["partial", "failed"]
    failure = (await clients[0].get(f"{base}/assets/{ids[1]}")).json()["error"]
    assert failure and failure != "Activity task failed"
    assert source.read_bytes() == Path(".local/fixtures/SYNTHETIC-red-blue-speech.mp4").read_bytes()
    shutil.rmtree(root)
