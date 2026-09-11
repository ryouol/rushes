from fastapi import Depends, FastAPI, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.trustedhost import TrustedHostMiddleware

from rushes.api_common import DB, Access, row_json
from rushes.auth import (
    UserCreate,
    UserRead,
    backend,
    current_user,
    require_editor,
    users,
)
from rushes.config import settings
from rushes.db import get_session
from rushes.models import LedgerEntry, Membership, Project, User, Workspace
from rushes.routes_collections import router as collections_router
from rushes.routes_exports import router as exports_router
from rushes.routes_media import router as media_router
from rushes.routes_organization import router as organization_router
from rushes.routes_search import router as search_router
from rushes.routes_settings import router as settings_router
from rushes.security import OriginBoundary, RequestBodyBoundary

app = FastAPI(title="RUSHES API", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(RequestBodyBoundary)
app.add_middleware(OriginBoundary)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])
app.include_router(users.get_auth_router(backend), prefix="/api/auth")
app.include_router(users.get_register_router(UserRead, UserCreate), prefix="/api/auth")


class NamedInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)


class ProjectInput(NamedInput):
    description: str = Field(default="", max_length=2000)


@app.get("/api/health")
async def health():
    return {"status": "ok", "application": "RUSHES"}


@app.get("/api/auth/me", response_model=UserRead)
async def me(user: User = Depends(current_user)):
    return user


@app.get("/api/workspaces")
async def list_workspaces(user: User = Depends(current_user), session=Depends(get_session)):
    results = await session.execute(
        select(Workspace, Membership.role)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Membership.user_id == user.id)
    )
    return [
        {"id": ws.id, "name": ws.name, "role": role, "balance_milli": ws.balance_milli}
        for ws, role in results
    ]


@app.post("/api/workspaces", status_code=201)
async def create_workspace(
    body: NamedInput,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    workspace = Workspace(
        name=body.name, owner_id=user.id, balance_milli=settings().local_credits * 1000
    )
    session.add(workspace)
    await session.flush()
    session.add(Membership(workspace_id=workspace.id, user_id=user.id, role="owner"))
    await session.execute(
        text("SELECT set_config('rushes.workspace_id', :workspace, true)"),
        {"workspace": str(workspace.id)},
    )
    session.add(
        LedgerEntry(
            workspace_id=workspace.id,
            operation_key=f"grant:{workspace.id}",
            kind="local_development_grant",
            delta_milli=workspace.balance_milli,
            balance_milli=workspace.balance_milli,
            description="Explicit local development credits; no payment collected",
        )
    )
    await session.commit()
    return {
        "id": workspace.id,
        "name": workspace.name,
        "role": "owner",
        "balance_milli": workspace.balance_milli,
    }


@app.get("/api/workspaces/{workspace_id}/projects")
async def list_projects(
    db: DB, access: Access, offset: int = Query(0, ge=0), limit: int = Query(40, ge=1, le=100)
):
    projects = await db.scalars(
        select(Project)
        .where(Project.workspace_id == access.workspace_id)
        .order_by(Project.created_at.desc(), Project.id)
        .offset(offset)
        .limit(limit)
    )
    total = await db.scalar(
        select(func.count()).select_from(Project).where(Project.workspace_id == access.workspace_id)
    )
    return {"items": [row_json(project) for project in projects], "total": total}


@app.post("/api/workspaces/{workspace_id}/projects", status_code=201)
async def create_project(body: ProjectInput, db: DB, access: Access):
    require_editor(access)
    project = Project(workspace_id=access.workspace_id, **body.model_dump())
    db.add(project)
    await db.flush()
    return row_json(project)


app.include_router(media_router)
app.include_router(organization_router)

app.include_router(search_router)
app.include_router(collections_router)

app.include_router(exports_router)

app.include_router(settings_router)
