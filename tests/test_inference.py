import pytest
from pydantic import ValidationError
from rushes.inference import AnalysisResponse, analysis_cache_key, validated_intervals
from rushes.timing import Interval


def test_model_configuration_rejected_before_provider_upload():
    from rushes.config import Settings, settings
    from rushes.inference import GeminiAnalyzer

    with pytest.raises(ValueError, match="supports gemini-3.6-flash"):
        GeminiAnalyzer("gemini-2.5-pro")
    with pytest.raises(ValidationError, match="supports gemini-3.6-flash"):
        Settings.model_validate({**settings().model_dump(), "gemini_model": "gemini-2.5-pro"})


def test_model_offsets_are_validated_then_translated():
    response = AnalysisResponse.model_validate(
        {
            "observations": [
                {
                    "kind": "visual_event",
                    "description": "Synthetic event",
                    "start_seconds": 1.25,
                    "end_seconds": 2.5,
                    "uncertainty": "medium",
                }
            ]
        }
    )
    window = Interval(start_us=60_000_000, end_us=120_000_000)
    _, interval = validated_intervals(response, window, 120_000_000)[0]
    assert interval == Interval(start_us=61_250_000, end_us=62_500_000)
    with pytest.raises(ValueError):
        validated_intervals(response, Interval(start_us=0, end_us=1_000_000), 1_000_000)


def test_nonfinite_model_timestamp_rejected():
    with pytest.raises(ValidationError):
        AnalysisResponse.model_validate(
            {
                "observations": [
                    {
                        "kind": "visual_event",
                        "description": "test",
                        "start_seconds": 0,
                        "end_seconds": float("inf"),
                        "uncertainty": "high",
                    }
                ]
            }
        )


def test_cache_key_covers_material_inputs():
    arguments = dict(
        fingerprint="abc",
        window=Interval(start_us=0, end_us=1_000_000),
        transcript_hash="original",
        model="model-a",
        sampling={"fps": 1},
        run_request="initial",
    )
    key = analysis_cache_key(**arguments)
    for field, value in [
        ("fingerprint", "xyz"),
        ("transcript_hash", "edited"),
        ("model", "model-b"),
        ("sampling", {"fps": 2}),
        ("window", Interval(start_us=0, end_us=2_000_000)),
    ]:
        assert analysis_cache_key(**{**arguments, field: value}) != key


@pytest.mark.parametrize("failure", ["transient_status", "persistent_status", "generation"])
def test_status_reads_retry_but_generation_never_repeats(monkeypatch, tmp_path, failure):
    from collections import Counter
    from types import SimpleNamespace

    from google import genai
    from google.genai import errors
    from pydantic import SecretStr
    from rushes import inference
    from rushes.config import settings

    monkeypatch.setattr(settings(), "gemini_api_key", SecretStr("synthetic-no-network"))
    calls = Counter()
    monkeypatch.setattr(inference, "reserve_provider_call", lambda _: calls.update(["reserve"]))
    monkeypatch.setattr(inference.time, "sleep", lambda _: None)

    def remote(state):
        return SimpleNamespace(
            name="files/synthetic",
            expiration_time=None,
            uri="https://example.invalid/clip",
            state=SimpleNamespace(name=state),
        )

    def upload(**kwargs):
        calls.update(["upload"])
        return remote("PROCESSING")

    def status(**kwargs):
        calls.update(["status"])
        if failure == "persistent_status" or failure == "transient_status" and calls["status"] == 1:
            raise errors.ServerError(500, {"error": {"message": "Synthetic file-status failure"}})
        return remote("ACTIVE")

    def generate(**kwargs):
        calls.update(["generate"])
        if failure == "generation":
            raise errors.ServerError(503, {"error": {"message": "Synthetic ambiguous generation"}})
        return SimpleNamespace(
            text='{"observations":[]}', model_dump=lambda **kw: {}, usage_metadata=None
        )

    client = SimpleNamespace(
        files=SimpleNamespace(
            upload=upload, get=status, delete=lambda **kw: calls.update(["delete"])
        ),
        models=SimpleNamespace(
            count_tokens=lambda **kw: SimpleNamespace(total_tokens=100), generate_content=generate
        ),
        close=lambda: calls.update(["close"]),
    )
    monkeypatch.setattr(genai, "Client", lambda **kw: client)

    def analyze():
        return inference.GeminiAnalyzer().analyze(
            tmp_path / "synthetic.mp4", Interval(start_us=0, end_us=1_000_000), ""
        )

    if failure == "generation":
        with pytest.raises(errors.ServerError):
            analyze()
        assert calls["status"] == 1 and calls["generate"] == 1
    else:
        result = analyze()
        if failure == "persistent_status":
            assert result.provider_outcome == "preparation_failed" and result.input_tokens == 0
            assert calls["status"] == 3 and calls["generate"] == 0
        else:
            assert result.provider_outcome == "received"
            assert calls["status"] == 2 and calls["generate"] == 1
    assert calls["reserve"] == calls["upload"] == calls["delete"] == calls["close"] == 1
