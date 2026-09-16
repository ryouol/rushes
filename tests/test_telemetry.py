import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from rushes.telemetry import TraceActivities, context, span, traced


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


async def test_trace_context_follows_threads_and_restores_after_failure(tmp_path, monkeypatch):
    path = tmp_path / "spans.jsonl"
    monkeypatch.setenv("RUSHES_TRACE_FILE", str(path))

    @traced("thread")
    def threaded():
        return context()["trace_id"]

    with pytest.raises(ValueError), span("upload") as parent:
        assert await asyncio.to_thread(threaded) == parent["trace_id"]
        raise ValueError("sensitive provider content")
    rows = records(path)
    assert rows[1]["parent_span_id"] == rows[0]["span_id"]
    assert rows[-1]["status"] == "ValueError"
    assert "sensitive" not in path.read_text()
    assert context() == {}


async def test_activity_attempts_link_job_and_separate_queue_wait(tmp_path, monkeypatch):
    path = tmp_path / "spans.jsonl"
    monkeypatch.setenv("RUSHES_TRACE_FILE", str(path))
    now = datetime.now(UTC)
    info = SimpleNamespace(
        workflow_id="workflow",
        workflow_run_id="run-1",
        activity_id="2",
        activity_type="transcribe",
        attempt=1,
        task_queue="media",
        started_time=now,
        scheduled_time=now - timedelta(seconds=100),
        current_attempt_scheduled_time=now - timedelta(seconds=3),
    )
    monkeypatch.setattr("rushes.telemetry.activity.info", lambda: info)

    class Next:
        async def execute_activity(self, input):
            return "checkpoint-reused"

    interceptor = TraceActivities(Next())
    input = SimpleNamespace(args=[{"job_id": "logical-job"}])
    assert await interceptor.execute_activity(input) == "checkpoint-reused"
    info.attempt, info.workflow_run_id = 2, "run-2"
    await interceptor.execute_activity(input)
    ended = [r for r in records(path) if r["event"] == "end"]
    assert ended[0]["trace_id"] == ended[1]["trace_id"]
    assert ended[0]["span_id"] != ended[1]["span_id"]
    assert [r["attempt"] for r in ended] == [1, 2]
    assert ended[0]["queue_wait_ns"] == 3_000_000_000
    assert ended[0]["duration_ns"] < ended[0]["queue_wait_ns"]


def test_unavailable_sink_does_not_retry_completed_work(monkeypatch, tmp_path):
    monkeypatch.setenv("RUSHES_TRACE_FILE", str(tmp_path / "missing" / "trace"))
    with span("committed"):
        pass
