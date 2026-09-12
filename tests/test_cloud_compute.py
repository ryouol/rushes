import hashlib
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from google import genai
from google.genai import types
from pydantic import SecretStr, ValidationError
from rushes import activities, inference, remote_compute
from rushes.config import settings
from rushes.db import tenant_session
from rushes.inference import AnalysisResponse, GeminiAnalyzer
from rushes.models import Embedding, Job
from rushes.timing import Interval
from sqlalchemy import select


def test_gemini_schema_passes_real_sdk_and_retains_local_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(inference, "reserve_provider_call", lambda _: None)
    payloads, deleted = [], []
    output = {
        "observations": [
            {
                "kind": "visual_event",
                "start_seconds": 0,
                "end_seconds": 1,
                "description": "Synthetic event",
                "uncertainty": "high",
            }
        ]
    }

    def respond(request):
        body = json.loads(request.content)
        payloads.append(body)
        if request.url.path.endswith(":countTokens"):
            return httpx.Response(200, json={"totalTokens": 123})
        assert request.url.path.endswith(":generateContent")
        config = body["generationConfig"]
        schema = json.dumps(config["responseSchema"])
        for unsupported in (
            "additionalProperties",
            "exclusiveMinimum",
            "minLength",
            "maxLength",
            "minimum",
            "maxItems",
        ):
            assert unsupported not in schema
        assert config["thinkingConfig"] == {"thinking_level": "MINIMAL"}
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"role": "model", "parts": [{"text": json.dumps(output)}]}}
                ],
                "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 30},
            },
        )

    client_type = genai.Client

    def client(**kwargs):
        options = kwargs["http_options"]
        options.client_args = {"transport": httpx.MockTransport(respond)}
        result = client_type(**kwargs)
        result._files = SimpleNamespace(
            upload=lambda **_: types.File(
                name="files/synthetic", uri="https://example.invalid/synthetic", state="ACTIVE"
            ),
            delete=lambda **kw: deleted.append(kw["name"]),
        )
        return result

    monkeypatch.setattr(genai, "Client", client)
    monkeypatch.setattr(settings(), "gemini_api_key", SecretStr("synthetic-no-network"))
    result = GeminiAnalyzer().analyze(
        tmp_path / "synthetic.mp4", Interval(start_us=0, end_us=1_000_000), "Synthetic transcript"
    )
    assert (result.preflight_tokens, result.input_tokens, result.output_tokens) == (123, 120, 30)
    assert len(payloads) == 2 and deleted == ["files/synthetic"]
    assert AnalysisResponse.model_validate_json(result.text).observations[0].end_seconds == 1
    for override in ({"extra": True}, {"description": "x" * 2001}, {"end_seconds": 0}):
        with pytest.raises(ValidationError):
            AnalysisResponse.model_validate(
                {"observations": [{**output["observations"][0], **override}]}
            )


@pytest.mark.parametrize(
    "response",
    [
        {"model": "wrong", "vectors": [[0.0] * 384]},
        {"model": remote_compute.REMOTE_EMBEDDING_MODEL, "vectors": []},
        {"model": remote_compute.REMOTE_EMBEDDING_MODEL, "vectors": [[0.0] * 383]},
        {"model": remote_compute.REMOTE_EMBEDDING_MODEL, "vectors": [[float("nan")] * 384]},
    ],
)
def test_invalid_remote_vectors_are_rejected(monkeypatch, response):
    monkeypatch.setattr(remote_compute, "reserve_provider_call", lambda _: None)
    monkeypatch.setattr(
        remote_compute, "remote_function", lambda _: SimpleNamespace(remote=lambda _: response)
    )
    with pytest.raises(ValueError):
        remote_compute.RemoteEmbedder().embed(["Synthetic"])


def test_remote_limits_prevent_dispatch_and_reject_shifted_timestamps(tmp_path, monkeypatch):
    monkeypatch.setattr(remote_compute, "reserve_provider_call", lambda _: None)
    calls = []

    def dispatch(name):
        calls.append(name)
        return SimpleNamespace(
            remote=lambda *_: {
                "model": "tiny",
                "segments": [
                    {"start_us": 0, "end_us": 1_000_000, "text": "Incorrect source offset"}
                ],
            }
        )

    monkeypatch.setattr(remote_compute, "remote_function", dispatch)
    for texts in ([], ["x"] * 33, ["🙂" * 4001]):
        with pytest.raises(ValueError):
            remote_compute.RemoteEmbedder().embed(texts)
    path = tmp_path / "derived.wav"
    path.write_bytes(b"x" * (remote_compute.MAX_AUDIO_BYTES + 1))
    with pytest.raises(ValueError):
        remote_compute.transcribe_remote(path, Interval(start_us=0, end_us=1_000_000))
    path.write_bytes(b"synthetic")
    with pytest.raises(ValueError):
        remote_compute.transcribe_remote(path, Interval(start_us=0, end_us=60_000_001))
    assert calls == []
    with pytest.raises(ValueError, match="outside its source window"):
        remote_compute.transcribe_remote(path, Interval(start_us=60_000_000, end_us=61_000_000))
    assert calls == ["transcribe_audio"]


@pytest.mark.integration
async def test_api_unicode_note_is_indexed_through_remote_contract(authenticated, monkeypatch):
    monkeypatch.setattr(remote_compute, "reserve_provider_call", lambda _: None)
    clients, ws, _, _, asset, _ = authenticated
    text = "🙂" * 4000
    batches = []

    def embed(texts):
        remote_compute.validate_texts(texts)
        batches.append(texts)
        return {
            "model": remote_compute.REMOTE_EMBEDDING_MODEL,
            "vectors": [[0.01] * 384 for _ in texts],
        }

    monkeypatch.setattr(remote_compute, "remote_function", lambda _: SimpleNamespace(remote=embed))
    monkeypatch.setattr(activities, "embedder", remote_compute.RemoteEmbedder)
    monkeypatch.setattr(activities, "heartbeat", lambda *_: None)
    response = await clients[0].post(
        f"/api/workspaces/{ws}/assets/{asset}/observations",
        json={"description": text, "start_us": 0, "end_us": 1_000_000, "request_id": str(uuid4())},
    )
    assert response.status_code == 201, response.text
    observation_id = UUID(response.json()["id"])
    async with tenant_session(ws) as db:
        job = await db.scalar(select(Job).where(Job.asset_id == asset, Job.kind == "index"))
        job.state = "running"
        job_id = job.id
    await activities.embed_asset(
        {"workspace_id": str(ws), "job_id": str(job_id), "asset_id": str(asset)}
    )
    async with tenant_session(ws) as db:
        stored = await db.scalar(
            select(Embedding).where(Embedding.observation_id == observation_id)
        )
        assert stored.dimension == 384
        assert stored.text_hash == hashlib.sha256(text.encode()).hexdigest()
    assert batches == [[text]]
