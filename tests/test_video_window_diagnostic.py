import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from google import genai
from google.genai import types
from pydantic import SecretStr


@pytest.mark.parametrize(
    "outcome", ["valid", "missing_usage", "bad_usage", "invalid_interval", "504"]
)
def test_comparison_uses_real_sdk_with_bounded_dispatch_and_strict_evidence(
    tmp_path, monkeypatch, outcome
):
    spec = importlib.util.spec_from_file_location(
        "video_window_diagnostic",
        Path(__file__).resolve().parents[1] / "scripts/compare_video_windows.py",
    )
    diagnostic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diagnostic)
    report = tmp_path / "report.json"
    monkeypatch.setattr(diagnostic, "ROOT", tmp_path)
    monkeypatch.setattr(diagnostic, "REPORT", report)
    monkeypatch.setattr(
        diagnostic,
        "settings",
        lambda: SimpleNamespace(
            gemini_api_key=SecretStr("synthetic-no-network"),
            gemini_model="gemini-3.6-flash",
            provider_monthly_allowance_microusd=2_000_000,
        ),
    )
    reservations, requests, deletions = [], [], []
    monkeypatch.setattr(diagnostic, "reserve_provider_call", reservations.append)

    def media(arguments, *, timeout):
        assert timeout == 60
        Path(arguments[-1]).write_bytes(b"synthetic-test-only")

    monkeypatch.setattr(diagnostic, "run_media", media)

    def respond(request):
        requests.append(request)
        body = json.loads(request.content)
        if request.url.path.endswith(":countTokens"):
            assert request.extensions["timeout"]["read"] == 30
            return httpx.Response(200, json={"totalTokens": 204})
        assert request.url.path.endswith(":generateContent")
        assert request.extensions["timeout"]["read"] == 120
        config = body["generationConfig"]
        assert config["maxOutputTokens"] == 512
        assert config["thinkingConfig"] == {"thinking_level": "MINIMAL"}
        schema = json.dumps(config["responseSchema"])
        assert "exclusiveMinimum" not in schema and "additionalProperties" not in schema
        if outcome == "504":
            return httpx.Response(
                504, json={"error": {"code": 504, "message": "Synthetic deadline"}}
            )
        part = body["contents"][0]["parts"][0]
        metadata = part["videoMetadata"]
        offset = 4 if len(reservations) == 1 else 0
        if offset:
            assert metadata["start_offset"] == "4s" and metadata["end_offset"] == "10s"
        else:
            assert "start_offset" not in metadata and "end_offset" not in metadata
        intervals = [
            {"color": "red", "start_seconds": offset, "end_seconds": offset + 1},
            {"color": "blue", "start_seconds": offset + 1, "end_seconds": offset + 6},
        ]
        if outcome == "invalid_interval":
            intervals[0]["end_seconds"] = intervals[0]["start_seconds"]
        payload = {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [{"text": json.dumps({"intervals": intervals})}],
                    }
                }
            ],
        }
        if outcome != "missing_usage":
            payload["usageMetadata"] = {
                "promptTokenCount": 204,
                "candidatesTokenCount": 50,
                "totalTokenCount": 253 if outcome == "bad_usage" else 254,
            }
        return httpx.Response(200, json=payload)

    client_type = genai.Client

    def client(**kwargs):
        kwargs["http_options"].client_args["transport"] = httpx.MockTransport(respond)
        instance = client_type(**kwargs)
        instance._files = SimpleNamespace(
            upload=lambda **_: types.File(
                name="files/synthetic", uri="https://example.invalid/synthetic", state="ACTIVE"
            ),
            delete=lambda **kw: deletions.append(kw["name"]),
            list=lambda **_: [],
        )
        return instance

    monkeypatch.setattr(genai, "Client", client)
    if outcome == "valid":
        diagnostic.main()
    else:
        with pytest.raises(SystemExit) as error:
            diagnostic.main()
        assert error.value.code == 1
    data = json.loads(report.read_text())
    assert data["passed"] is (outcome == "valid")
    dispatch_count = 1 if outcome == "504" else 2
    assert len(requests) == dispatch_count * 2
    assert reservations == ["gemini"] * dispatch_count
    assert deletions == ["files/synthetic"] * dispatch_count
    assert all(run["cleanup_verified"] and run["generation_dispatched"] for run in data["runs"])
    if outcome == "valid":
        assert data["runs"][0]["source_absolute_match"]
        assert not data["runs"][0]["clip_relative_match"]
        assert data["runs"][1]["clip_relative_match"]
    with pytest.raises(SystemExit, match="already recorded"):
        diagnostic.main()
    assert len(requests) == dispatch_count * 2
    assert reservations == ["gemini"] * dispatch_count
