from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from google import genai
from google.genai import errors
from pydantic import SecretStr
from rushes import inference, maintenance
from rushes.config import settings
from rushes.provider_files import delete_provider_file
from rushes.timing import Interval


@pytest.mark.parametrize(
    "expires_at", [None, datetime(2099, 1, 1, tzinfo=UTC), datetime(2000, 1, 1)]
)
@pytest.mark.parametrize("code", [403, 404])
def test_denied_or_unknown_file_lifetime_does_not_prove_deletion(expires_at, code):
    def delete(**_):
        raise errors.ClientError(code, {"error": {"message": "Synthetic absent or denied file"}})

    client = SimpleNamespace(files=SimpleNamespace(delete=delete))
    if code == 404:
        delete_provider_file(client, "files/synthetic", expires_at)
    else:
        with pytest.raises(errors.ClientError):
            delete_provider_file(client, "files/synthetic", expires_at)


def test_authoritative_expiry_needs_no_provider_client_or_request(monkeypatch):
    def unexpected(**_):
        pytest.fail("Expired cleanup must not create a provider client")

    monkeypatch.setattr(genai, "Client", unexpected)
    expiry = datetime.now(UTC) - timedelta(minutes=1)
    delete_provider_file(None, "files/synthetic", expiry)
    maintenance.delete_remote("files/synthetic", expiry)


@pytest.mark.parametrize("checkpoint_fails", [False, True])
def test_upload_expiry_survives_checkpoint_and_cleanup_failures(
    monkeypatch, tmp_path, checkpoint_fails
):
    expiry = datetime.now(UTC) + timedelta(hours=48)
    events = []
    monkeypatch.setattr(settings(), "gemini_api_key", SecretStr("synthetic-no-network"))
    monkeypatch.setattr(inference, "reserve_provider_call", lambda _: None)

    def checkpoint(name, expires_at):
        events.append(("checkpoint", name, expires_at))
        if checkpoint_fails:
            raise RuntimeError("Synthetic checkpoint failure")

    def delete(**_):
        raise errors.ClientError(403, {"error": {"message": "Synthetic cleanup denied"}})

    def generate(**_):
        events.append(("generate",))
        return SimpleNamespace(
            text='{"observations":[]}', usage_metadata=None, model_dump=lambda **_: {}
        )

    client = SimpleNamespace(
        files=SimpleNamespace(
            upload=lambda **_: SimpleNamespace(
                name="files/synthetic",
                expiration_time=expiry,
                state=SimpleNamespace(name="ACTIVE"),
                uri="https://example.invalid/synthetic",
            ),
            delete=delete,
        ),
        models=SimpleNamespace(
            count_tokens=lambda **_: SimpleNamespace(total_tokens=1), generate_content=generate
        ),
        close=lambda: None,
    )
    monkeypatch.setattr(genai, "Client", lambda **_: client)
    result = inference.GeminiAnalyzer().analyze(
        tmp_path / "synthetic.mp4", Interval(start_us=0, end_us=1_000_000), "", checkpoint
    )
    assert events[0] == ("checkpoint", "files/synthetic", expiry)
    assert len(events) == (1 if checkpoint_fails else 2)
    assert result.provider_outcome == ("preparation_failed" if checkpoint_fails else "received")
    assert result.cleanup_pending_file == "files/synthetic"
    assert result.cleanup_pending_file_expires_at == expiry


def test_live_verifier_accepts_upload_lifetime_callback_offline(monkeypatch, tmp_path):
    import importlib.util
    import json
    from contextlib import nullcontext
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts/verify_gemini.py"
    spec = importlib.util.spec_from_file_location("verify_gemini_offline", path)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    monkeypatch.chdir(tmp_path)
    fixture = Path(".local/fixtures/SYNTHETIC-red-blue-speech.mp4")
    fixture.parent.mkdir(parents=True)
    fixture.write_bytes(b"Synthetic offline callback fixture")
    Path("docs/validation").mkdir(parents=True)
    monkeypatch.setattr(settings(), "gemini_api_key", SecretStr("synthetic-no-network"))
    monkeypatch.setattr(verifier.subprocess, "check_output", lambda *_args, **_kwargs: "1")

    def analyze(_fixture, _window, _transcript, checkpoint):
        checkpoint("files/synthetic", datetime.now(UTC) + timedelta(hours=48))
        return inference.AnalysisResult(raw={}, model="synthetic", text='{"observations":[]}')

    monkeypatch.setattr(verifier, "GeminiAnalyzer", lambda: SimpleNamespace(analyze=analyze))
    monkeypatch.setattr(
        verifier.genai,
        "Client",
        lambda **_: nullcontext(SimpleNamespace(files=SimpleNamespace(list=lambda **_: []))),
    )
    verifier.main()
    report = json.loads(Path("docs/validation/gemini-live.json").read_text())
    assert report["passed"] and report["provider_files"] == ["files/synthetic"]
