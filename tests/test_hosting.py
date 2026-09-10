import pytest
from pydantic import ValidationError
from rushes.config import Settings, settings


@pytest.mark.parametrize(
    "origin",
    [
        "http://rushes.example.com",
        "https://user:secret@rushes.example.com",
        "https://rushes.example.com/private",
        "https://rushes.example.com?secret=yes",
        "https://rushes.example.com#fragment",
        "https://rushes.example.com?",
        "https://rushes.example.com#",
        "file:///etc/passwd",
    ],
)
def test_invalid_public_origins_are_rejected(origin):
    with pytest.raises(ValidationError):
        Settings.model_validate({**settings().model_dump(), "origin": origin})


@pytest.mark.parametrize("origin", ["https://rushes.example.com", "http://localhost:3841"])
def test_runtime_does_not_require_migration_credentials(origin):
    config = Settings.model_validate(
        {**settings().model_dump(), "origin": origin, "admin_database_url": None}
    )
    assert config.origin == origin
    with pytest.raises(ValueError, match="Migration commands require"):
        config.require_admin_database_url()


async def test_hosted_origin_preserves_csrf_and_private_host_guards(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from rushes.api import app

    monkeypatch.setattr(settings(), "origin", "https://rushes.example.com")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        assert (
            await client.get("/api/health", headers={"Origin": "https://rushes.example.com"})
        ).status_code == 200
        assert (
            await client.get("/api/health", headers={"Origin": "https://other.example.com"})
        ).status_code == 403
        assert (
            await client.post("/api/workspaces", json={"name": "Unauthenticated"})
        ).status_code == 403
        assert (
            await client.post(
                "/api/workspaces",
                headers={"Origin": "https://rushes.example.com"},
                json={"name": "Unauthenticated"},
            )
        ).status_code == 401
        assert (
            await client.get("/api/health", headers={"Host": "rushes.example.com"})
        ).status_code == 400


async def test_trusted_client_identity_separates_auth_limits(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from rushes.security import OriginBoundary
    from starlette.responses import Response

    monkeypatch.setattr(settings(), "client_ip_header", "x-rushes-ingress-client-ip")

    async def handler(scope, receive, send):
        await Response(status_code=204)(scope, receive, send)

    boundary = OriginBoundary(handler)
    async with AsyncClient(
        transport=ASGITransport(app=boundary),
        base_url="http://127.0.0.1",
        headers={"Origin": settings().origin},
    ) as client:
        for _ in range(10):
            assert (
                await client.post("/api/auth/login", headers={"x-rushes-client-ip": "192.0.2.1"})
            ).status_code == 204
        assert (
            await client.post("/api/auth/login", headers={"x-rushes-client-ip": "192.0.2.1"})
        ).status_code == 429
        assert (
            await client.post("/api/auth/login", headers={"x-rushes-client-ip": "192.0.2.2"})
        ).status_code == 204
        assert (
            await client.post("/api/auth/login", headers={"X-Forwarded-For": "192.0.2.3"})
        ).status_code == 503
        assert (
            await client.post(
                "/api/auth/login", headers={"x-rushes-client-ip": "192.0.2.3, 192.0.2.4"}
            )
        ).status_code == 503


@pytest.mark.integration
async def test_expired_upload_leaves_no_asset_job_or_partial_file(
    authenticated, monkeypatch, tmp_path
):
    import asyncio

    from rushes.db import tenant_session
    from rushes.models import Asset, Job
    from sqlalchemy import func, select

    clients, workspace, _, project, _, _ = authenticated
    monkeypatch.setattr(settings(), "storage_root", tmp_path)
    monkeypatch.setattr(settings(), "upload_timeout_seconds", 1)

    async with tenant_session(workspace) as db:
        before = (
            await db.scalar(select(func.count()).select_from(Asset)),
            await db.scalar(select(func.count()).select_from(Job)),
        )

    async def stalled_upload():
        yield b"a partial source"
        await asyncio.sleep(2)
        yield b"never accepted"

    response = await clients[0].post(
        f"/api/workspaces/{workspace}/projects/{project}/upload?filename=timeout.mp4",
        content=stalled_upload(),
        headers={"Content-Type": "video/mp4"},
    )
    assert response.status_code == 408
    assert "Upload took too long" in response.json()["detail"]
    assert not list(tmp_path.rglob("*.part"))
    assert not list(tmp_path.rglob("original*"))
    async with tenant_session(workspace) as db:
        assert (
            await db.scalar(select(func.count()).select_from(Asset)),
            await db.scalar(select(func.count()).select_from(Job)),
        ) == before


@pytest.mark.integration
async def test_waiting_uploads_release_database_connections(authenticated, monkeypatch, tmp_path):
    import asyncio

    clients, workspace, _, project, _, _ = authenticated
    monkeypatch.setattr(settings(), "storage_root", tmp_path)
    release = asyncio.Event()
    waiting = [asyncio.Event() for _ in range(11)]

    async def body(index):
        yield b"x"
        waiting[index].set()
        await release.wait()

    tasks = [
        asyncio.create_task(
            clients[0].post(
                f"/api/workspaces/{workspace}/projects/{project}/upload?filename=waiting-{index}.mp4",
                content=body(index),
                headers={"Content-Length": "2"},
            )
        )
        for index in range(len(waiting))
    ]
    try:
        async with asyncio.timeout(5):
            await asyncio.gather(*(event.wait() for event in waiting))
            response = await clients[0].get(f"/api/workspaces/{workspace}/projects")
            assert response.status_code == 200
    finally:
        release.set()
        responses = await asyncio.gather(*tasks)
    assert all(response.status_code == 400 for response in responses)
    assert not list(tmp_path.rglob("*.part"))
    assert not list(tmp_path.rglob("original*"))


@pytest.mark.integration
async def test_upload_rechecks_membership_before_committing(authenticated, monkeypatch, tmp_path):
    from rushes.db import session_factory
    from rushes.models import Membership
    from sqlalchemy import select

    clients, workspace, _, project, _, _ = authenticated
    monkeypatch.setattr(settings(), "storage_root", tmp_path)

    async def body():
        yield b"part one"
        async with session_factory()() as db:
            membership = await db.scalar(
                select(Membership).where(
                    Membership.workspace_id == workspace, Membership.role == "owner"
                )
            )
            membership.role = "viewer"
            await db.commit()
        yield b"part two"

    response = await clients[0].post(
        f"/api/workspaces/{workspace}/projects/{project}/upload?filename=revoked.mp4",
        content=body(),
    )
    assert response.status_code == 403
    assert not list(tmp_path.rglob("*.part"))
    assert not list(tmp_path.rglob("original*"))
