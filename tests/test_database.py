import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from rushes.api import app
from rushes.credits import CreditError, reserve, settle
from rushes.db import session_factory, tenant_session
from rushes.models import LedgerEntry, Project, Workspace
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError


@pytest.mark.integration
async def test_runtime_role_cannot_bypass_rls_and_context_does_not_leak(account_workspace):
    async with session_factory()() as session:
        role = (
            await session.execute(
                text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user")
            )
        ).one()
        assert not role.rolsuper and not role.rolbypassrls
    async with tenant_session(account_workspace) as session:
        project = Project(workspace_id=account_workspace, name="Private project")
        session.add(project)
        await session.flush()
        project_id = project.id
    async with tenant_session(uuid.uuid4()) as session:
        assert await session.get(Project, project_id) is None
    async with session_factory()() as session:
        assert await session.get(Project, project_id) is None
    with pytest.raises(DBAPIError):
        async with tenant_session(uuid.uuid4()) as session:
            session.add(
                Project(workspace_id=account_workspace, name="Forbidden cross-tenant write")
            )
            await session.flush()


@pytest.mark.integration
async def test_credit_concurrency_and_idempotent_settlement(account_workspace):
    import asyncio

    async def claim(key):
        try:
            async with tenant_session(account_workspace) as session:
                await reserve(session, account_workspace, key, 800)
            return key
        except CreditError:
            return None

    keys = [f"test:{uuid.uuid4()}", f"test:{uuid.uuid4()}"]
    results = await asyncio.gather(*(claim(key) for key in keys))
    winner = next(result for result in results if result)
    assert results.count(None) == 1
    for _ in range(2):
        async with tenant_session(account_workspace) as session:
            await settle(session, account_workspace, winner, 500)
    async with tenant_session(account_workspace) as session:
        workspace = await session.get(Workspace, account_workspace)
        assert workspace.balance_milli == 500
        entries = list(
            await session.scalars(
                select(LedgerEntry).where(LedgerEntry.workspace_id == account_workspace)
            )
        )
        assert len(entries) == 2


@pytest.mark.integration
async def test_real_signup_login_logout_and_tenant_denial():
    origin = {"Origin": "http://localhost:3741"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost", headers=origin
    ) as alice:
        email = f"alice-{uuid.uuid4()}@example.com"
        response = await alice.post(
            "/api/auth/register",
            json={"email": email, "password": "Synthetic-password-42", "name": "Alice"},
        )
        assert response.status_code == 201, response.text
        response = await alice.post(
            "/api/auth/login", data={"username": email, "password": "Synthetic-password-42"}
        )
        assert response.status_code == 204, response.text
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "SameSite=strict" in response.headers["set-cookie"]
        workspace = (await alice.post("/api/workspaces", json={"name": "Alice test"})).json()
        project = await alice.post(
            f"/api/workspaces/{workspace['id']}/projects", json={"name": "Private shoot"}
        )
        assert project.status_code == 201, project.text
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://localhost", headers=origin
        ) as bob:
            bob_email = f"bob-{uuid.uuid4()}@example.com"
            await bob.post(
                "/api/auth/register",
                json={"email": bob_email, "password": "Synthetic-password-42", "name": "Bob"},
            )
            await bob.post(
                "/api/auth/login", data={"username": bob_email, "password": "Synthetic-password-42"}
            )
            assert (await bob.get(f"/api/workspaces/{workspace['id']}/projects")).status_code == 404
        assert (await alice.post("/api/auth/logout")).status_code == 204
        assert (await alice.get("/api/auth/me")).status_code == 401


async def test_untrusted_origin_and_host_denied():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as client:
        assert (await client.post("/api/auth/register", json={})).status_code == 403
        assert (
            await client.get("/api/health", headers={"Origin": "https://evil.example"})
        ).status_code == 403
        assert (
            await client.get("/api/health", headers={"Host": "evil.example"})
        ).status_code == 400
