"""Run one bounded live video request and record validation without exposing credentials."""

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from google import genai
from google.genai import types
from rushes.config import settings
from rushes.inference import AnalysisResponse, GeminiAnalyzer, validated_intervals
from rushes.timing import Interval


def main():
    fixture = Path(".local/fixtures/SYNTHETIC-red-blue-speech.mp4")
    report_path = Path("docs/validation/gemini-live.json")
    digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
    duration = float(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(fixture),
            ],
            text=True,
        )
    )
    if not 0 < duration <= 20 or fixture.stat().st_size > 16 * 1024**2:
        raise SystemExit("Live verification requires the bounded synthetic fixture")
    window = Interval(start_us=0, end_us=round(duration * 1_000_000))
    remote_files = []
    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "scope": "One synthetic video request; not representative semantic quality or hosted integration",
        "model": settings().gemini_model,
        "source_sha256": digest,
        "duration_us": window.end_us,
        "passed": False,
    }
    try:
        result = GeminiAnalyzer().analyze(
            fixture, window, "", lambda name, _expires_at: remote_files.append(name)
        )
        report.update(
            provider_outcome=result.provider_outcome,
            input_tokens=result.input_tokens,
            preflight_tokens=result.preflight_tokens,
            output_tokens=result.output_tokens,
            usage_metadata=result.raw.get("usage_metadata"),
            cleanup_pending=bool(result.cleanup_pending_file),
        )
        response = AnalysisResponse.model_validate_json(result.text or "")
        validated_intervals(response, window, window.end_us)
        report.update(
            observations=response.model_dump()["observations"],
            interval_validation_passed=True,
            source_preserved=hashlib.sha256(fixture.read_bytes()).hexdigest() == digest,
        )
        with genai.Client(
            api_key=settings().gemini_api_key.get_secret_value(),
            http_options=types.HttpOptions(
                timeout=30_000, retry_options=types.HttpRetryOptions(attempts=1)
            ),
        ) as client:
            remaining = set()
            for index, file in enumerate(client.files.list(config={"page_size": 100})):
                if index >= 1000:
                    raise ValueError("Provider file inventory exceeds verification bound")
                remaining.add(file.name)
        report["provider_files"] = remote_files
        report["provider_file_deletion_verified"] = (
            len(remote_files) == 1
            and not result.cleanup_pending_file
            and not remaining.intersection(remote_files)
        )
        report["passed"] = report["source_preserved"] and report["provider_file_deletion_verified"]
    except Exception as error:
        report.update(error_type=type(error).__name__, error_code=getattr(error, "code", None))
        message = str(error).replace(settings().gemini_api_key.get_secret_value(), "[redacted]")
        report["error_message"] = message[:1500]
        if hasattr(error, "errors"):
            report["validation_errors"] = error.errors(include_input=False, include_url=False)
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
