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
