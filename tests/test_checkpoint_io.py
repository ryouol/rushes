import asyncio
import json
import threading
from pathlib import Path

import pytest
from rushes import pipeline
from rushes.config import settings
from rushes.db import tenant_session
from rushes.models import Observation
from sqlalchemy import select


@pytest.mark.integration
@pytest.mark.parametrize("paused_operation", ["checkpoint", "audio_cleanup"])
async def test_canceled_transcription_drains_and_reuses_its_checkpoint(
    authenticated, monkeypatch, tmp_path, paused_operation
):
    clients, workspace, _other, _project, asset, _tokens = authenticated
    monkeypatch.setattr(settings(), "storage_root", tmp_path / "storage")
    folder = pipeline.asset_folder(str(workspace), str(asset))
    timeline = {
        "duration_us": 1_000_000,
        "time_base": "1/24",
        "first_pts": 0,
        "last_pts": 23,
        "frame_count": 24,
        "average_rate": "24",
        "nominal_rate": "24",
        "constant_frame_rate": True,
        "source_timecode": None,
        "drop_frame": None,
        "width": 160,
        "height": 90,
        "rotation": 0,
        "has_audio": True,
        "codec": "h264",
        "frame_map": "synthetic.jsonl.gz",
    }
    (folder / "manifest.json").write_text(
        json.dumps(
            {
                "source": timeline,
                "proxy": timeline,
                "source_hash": "synthetic-checkpoint-fixture",
            }
        )
    )
    audio = folder / "synthetic.wav"
    audio.write_bytes(b"synthetic mocked audio")
    calls = []

    def transcribe(*_args):
        calls.append("transcribed")
        return [
            {
                "start_us": 0,
                "end_us": 500_000,
                "text": "Retain this transcript",
                "language": "en",
                "words": [],
            }
        ]

    monkeypatch.setattr(pipeline, "prepare_audio", lambda *_: audio)
    monkeypatch.setattr(pipeline, "transcribe", transcribe)
    entered, release = threading.Event(), threading.Event()
    original = pipeline.save_transcript

    def pause():
        entered.set()
        assert release.wait(3), "Checkpoint storage blocked the API event loop"

    def slow_checkpoint(*args):
        original(*args)
        if paused_operation == "checkpoint":
            pause()

    unlink = Path.unlink

    def slow_cleanup(path, **kwargs):
        unlink(path, **kwargs)
        if path == audio and paused_operation == "audio_cleanup":
            pause()

    monkeypatch.setattr(Path, "unlink", slow_cleanup)
    monkeypatch.setattr(pipeline, "save_transcript", slow_checkpoint)
    task = asyncio.create_task(pipeline.transcribe_asset(str(workspace), str(asset)))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        assert (await asyncio.wait_for(clients[0].get("/api/health"), 1)).status_code == 200
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), "Cancellation must drain the checkpoint writer"
    finally:
        release.set()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
    assert not audio.exists()
    result = await pipeline.transcribe_asset(str(workspace), str(asset))
    assert result == {"state": "completed", "segments": 1}
    assert calls == ["transcribed"]
    async with tenant_session(workspace) as db:
        rows = list(await db.scalars(select(Observation).where(Observation.asset_id == asset)))
        assert [row.description for row in rows] == ["Retain this transcript"]
