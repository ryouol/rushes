import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from rushes.api import app
from rushes.config import settings
from rushes.db import session_factory, tenant_session
from rushes.models import AccessToken, Asset, MediaTimeline, Membership, Project, User, Workspace


@pytest.fixture
async def account_workspace():
    async with session_factory()() as session:
        user = User(
            email=f"test-{uuid.uuid4()}@example.com", hashed_password="test-only-unusable-hash"
        )
        session.add(user)
        await session.flush()
        workspace = Workspace(name="Synthetic test workspace", owner_id=user.id, balance_milli=1000)
        session.add(workspace)
        await session.commit()
        return workspace.id


@pytest.fixture
async def authenticated(monkeypatch):
    users, tokens = [], []
    async with session_factory()() as db:
        for name in ("owner", "viewer", "outsider"):
            user = User(
                email=f"{name}-{uuid.uuid4()}@example.com", hashed_password="unusable-test-password"
            )
            db.add(user)
            await db.flush()
            token = str(uuid.uuid4())
            db.add(AccessToken(token=token, user_id=user.id))
            users.append(user)
            tokens.append(token)
        workspace = Workspace(
            name="Authorization fixture", owner_id=users[0].id, balance_milli=1000
        )
        other = Workspace(name="Other fixture", owner_id=users[2].id)
        db.add_all([workspace, other])
        await db.flush()
        for user, role, ws in [
            (users[0], "owner", workspace),
            (users[1], "viewer", workspace),
            (users[2], "owner", other),
        ]:
            db.add(Membership(workspace_id=ws.id, user_id=user.id, role=role))
        await db.commit()
    folder = settings().storage_root / "test-media" / str(uuid.uuid4())
    folder.mkdir(parents=True)
    monkeypatch.setattr(settings(), "source_roots", [*settings().source_roots, folder])
    preview = folder / "test.mp4"
    preview.write_bytes(b"0123456789")
    async with tenant_session(workspace.id) as db:
        project = Project(workspace_id=workspace.id, name="Authorization test")
        db.add(project)
        await db.flush()
        asset = Asset(
            workspace_id=workspace.id,
            project_id=project.id,
            name="Synthetic.mp4",
            source_root=str(folder),
            relative_path=preview.name,
            duration_us=10_000_000,
            proxy_path=str(preview),
            status="partial",
        )
        db.add(asset)
        await db.flush()
        db.add(
            MediaTimeline(
                workspace_id=workspace.id,
                asset_id=asset.id,
                kind="source",
                details={"duration_us": 10_000_000},
            )
        )
    clients = [
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://localhost",
            headers={"Origin": settings().origin},
            cookies={"rushes_session": token},
        )
        for token in tokens
    ]
    try:
        yield clients, workspace.id, other.id, project.id, asset.id, tokens
    finally:
        for client in clients:
            await client.aclose()
        # Integration fixtures must not leave fake workflow IDs in the live outbox.
        from rushes.activities import finalize_failure
        from rushes.models import Job
        from sqlalchemy import select

        async with tenant_session(workspace.id) as db:
            jobs = list(
                await db.scalars(
                    select(Job).where(
                        Job.state.in_(["queued", "dispatched", "running", "cancel_requested"])
                    )
                )
            )
            for job in jobs:
                await finalize_failure(
                    db,
                    {
                        "workspace_id": str(workspace.id),
                        "job_id": str(job.id),
                        "state": "canceled",
                        "error": "Synthetic fixture teardown",
                    },
                )
        preview.unlink(missing_ok=True)
        folder.rmdir()
