"""Guard benchmark math against small-sample percentile and missing-success errors."""

import importlib.util
import sys
from pathlib import Path

import pytest


def test_nearest_rank_percentiles():
    folder = Path(__file__).parents[1] / "scripts"
    sys.path.insert(0, str(folder))
    try:
        spec = importlib.util.spec_from_file_location(
            "benchmark_pipeline", folder / "benchmark_pipeline.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.percentile([5, 1, 3, 2, 4], 0.5) == 3
        assert module.percentile([5, 1, 3, 2, 4], 0.95) == 5
    finally:
        sys.path.remove(str(folder))


@pytest.mark.asyncio
async def test_trace_boundary_validates_carrier_and_does_not_record_queries(tmp_path, monkeypatch):
    import json

    from rushes.telemetry import TraceBoundary, context

    path = tmp_path / "trace.jsonl"
    monkeypatch.setenv("RUSHES_TRACE_FILE", str(path))
    seen = []

    async def app(scope, receive, send):
        seen.append(context())

    boundary = TraceBoundary(app)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/search",
        "query_string": b"q=private",
        "headers": [(b"traceparent", b"00-" + b"a" * 32 + b"-" + b"b" * 16 + b"-01")],
    }
    await boundary(scope, None, None)
    assert seen[0]["trace_id"] == "a" * 32
    scope["headers"] = [(b"traceparent", b"00-" + b"0" * 32 + b"-" + b"0" * 16 + b"-01")]
    await boundary(scope, None, None)
    assert seen[1]["trace_id"] != "0" * 32
    assert "private" not in path.read_text()
    assert json.loads(path.read_text().splitlines()[0])["parent_span_id"] == "b" * 16
