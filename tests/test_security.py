import json
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from rushes.api import app
from rushes.config import settings
from rushes.routes_media import Correction, IndexInput
from rushes.security import MAX_INDEX_REQUEST_BYTES, MAX_REQUEST_BYTES, RequestBodyBoundary

PROJECT_PATH = f"/api/workspaces/{uuid.uuid4()}/projects/{uuid.uuid4()}"


async def test_declared_oversized_signup_is_rejected_without_reading_body(monkeypatch):
    monkeypatch.setattr(settings(), "client_ip_header", None)
    consumed = False

    async def body():
        nonlocal consumed
        consumed = True
        yield b"must not be read"

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.42", 123)),
        base_url="http://localhost",
        headers={"Origin": settings().origin},
    ) as client:
        response = await client.post(
            "/api/auth/register",
            content=body(),
            headers={"Content-Length": str(MAX_REQUEST_BYTES + 1)},
        )
    assert response.status_code == 413
    assert not consumed
    assert len(response.content) < 200


@pytest.mark.parametrize("declared", [None, "1"])
@pytest.mark.parametrize(
    ("path", "content_type", "prefix"),
    [
        ("/api/auth/register", "application/json", b'{"name":"'),
        ("/api/auth/login", "application/x-www-form-urlencoded", b"username="),
    ],
)
async def test_chunked_auth_bodies_stop_before_parsing_or_echoing_input(
    monkeypatch, declared, path, content_type, prefix
):
    monkeypatch.setattr(settings(), "client_ip_header", None)
    delivered = 0

    async def body():
        nonlocal delivered
        for chunk in [prefix, *([b"sensitive-input-" * 1024] * 100)]:
            delivered += len(chunk)
            yield chunk

    headers = {"Origin": settings().origin, "Content-Type": content_type}
    if declared is not None:
        headers["Content-Length"] = declared
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.42", 123)),
        base_url="http://localhost",
    ) as client:
        response = await client.post(path, content=body(), headers=headers)
    assert response.status_code == 413
    assert MAX_REQUEST_BYTES < delivered < MAX_REQUEST_BYTES + 16 * 1024
    assert b"sensitive-input" not in response.content
    assert len(response.content) < 200


async def test_largest_text_and_escaped_index_batch_fit_their_body_limits():
    probe = FastAPI()
    probe.add_middleware(RequestBodyBoundary)

    @probe.patch("/correction")
    async def correction(body: Correction):
        return {"characters": len(body.description)}

    @probe.post(PROJECT_PATH + "/index")
    async def index(body: IndexInput):
        return {"paths": len(body.paths)}

    # Astral Unicode uses twelve bytes per character with default JSON escaping.
    note = json.dumps(
        {"description": "\U0001f3ac" * 4000, "start_us": 0, "end_us": 1, "version": 1}
    ).encode()
    assert len(note) < MAX_REQUEST_BYTES
    note += b" " * (MAX_REQUEST_BYTES - len(note))
    # Each valid filesystem component is under 255 bytes, with worst-case JSON escaping.
    folder = ("\x01" * 240 + "/") * 16
    batch = json.dumps({"root": 0, "paths": [folder + f"{i}.mov" for i in range(200)]}).encode()
    assert 4 * 1024 * 1024 < len(batch) < MAX_INDEX_REQUEST_BYTES
    async with AsyncClient(
        transport=ASGITransport(app=probe), base_url="http://localhost"
    ) as client:
        response = await client.patch(
            "/correction", content=note, headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200 and response.json() == {"characters": 4000}
        response = await client.post(
            PROJECT_PATH + "/index", content=batch, headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200 and response.json() == {"paths": 200}

        async def oversized_batch():
            yield b" " * MAX_INDEX_REQUEST_BYTES
            yield b"x"

        response = await client.post(
            PROJECT_PATH + "/index",
            content=oversized_batch(),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 413 and len(response.content) < 200


@pytest.mark.integration
@pytest.mark.parametrize("declared", [False, True])
async def test_media_upload_keeps_its_own_stream_limit_and_role_checks(
    authenticated, monkeypatch, tmp_path, declared
):
    clients, workspace, _, project, _, _ = authenticated
    monkeypatch.setattr(settings(), "storage_root", tmp_path)
    monkeypatch.setattr(settings(), "min_free_bytes", 0)
    monkeypatch.setattr(settings(), "max_upload_bytes", MAX_REQUEST_BYTES + 1024)
    endpoint = f"/api/workspaces/{workspace}/projects/{project}/upload?filename=synthetic.mp4"
    headers = {"Content-Type": "video/mp4"}
    if declared:
        headers["Content-Length"] = str(MAX_REQUEST_BYTES + 2048)

    async def body():
        yield b"x" * MAX_REQUEST_BYTES
        yield b"x" * 2048

    response = await clients[1].post(endpoint, content=body(), headers=headers)
    assert response.status_code == 403
    response = await clients[0].post(endpoint, content=body(), headers=headers)
    assert response.status_code == 413
    assert response.json()["detail"] == "File exceeds the configured upload size limit"
    assert not list(tmp_path.rglob("upload.part"))
    assert not list(tmp_path.rglob("original*"))
