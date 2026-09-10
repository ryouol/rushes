import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, schemas
from fastapi_users.authentication import AuthenticationBackend, CookieTransport
from fastapi_users.authentication.strategy.db import DatabaseStrategy
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.exceptions import InvalidPasswordException
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rushes.config import settings
from rushes.db import get_session, session_factory, tenant_session
from rushes.models import AccessToken, Membership, User

SESSION_LIFETIME_SECONDS = 7 * 24 * 60 * 60


class UserRead(schemas.BaseUser[uuid.UUID]):
    name: str


class UserCreate(schemas.BaseUserCreate):
    name: str = Field(min_length=1, max_length=120)


async def user_database(session: AsyncSession = Depends(get_session)):
    yield SQLAlchemyUserDatabase(session, User)


async def token_database(session: AsyncSession = Depends(get_session)):
    yield SQLAlchemyAccessTokenDatabase(session, AccessToken)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    async def validate_password(self, password, user):
        if not 12 <= len(password) <= 256:
            raise InvalidPasswordException(reason="Use a password between 12 and 256 characters")


async def user_manager(database=Depends(user_database)):
    yield UserManager(database)


def database_strategy(database=Depends(token_database)):
    return DatabaseStrategy(database, lifetime_seconds=SESSION_LIFETIME_SECONDS)


transport = CookieTransport(
    cookie_name="rushes_session",
    cookie_max_age=SESSION_LIFETIME_SECONDS,
    cookie_secure=settings().origin.startswith("https:"),
    cookie_httponly=True,
    cookie_samesite="strict",
)
backend = AuthenticationBackend(name="cookie", transport=transport, get_strategy=database_strategy)
users = FastAPIUsers[User, uuid.UUID](user_manager, [backend])
current_user = users.current_user(active=True)


@dataclass(frozen=True)
class WorkspaceAccess:
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    role: str


async def workspace_access(
    workspace_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> WorkspaceAccess:
    membership = await session.scalar(
        select(Membership).where(
            Membership.workspace_id == workspace_id, Membership.user_id == user.id
        )
    )
    if membership is None:
        raise HTTPException(404, "Workspace not found")
    access = WorkspaceAccess(workspace_id, user.id, membership.role)
    await session.close()
    return access


def require_editor(access: WorkspaceAccess):
    if access.role not in {"owner", "editor"}:
        raise HTTPException(403, "An editor role is required")


async def workspace_db(access: WorkspaceAccess = Depends(workspace_access)):
    async with tenant_session(access.workspace_id) as session:
        yield session


async def stream_access(request: Request, workspace_id: uuid.UUID) -> WorkspaceAccess:
    """Close authentication transactions before an SSE connection waits for more events."""
    token = request.cookies.get("rushes_session")
    if not token:
        raise HTTPException(401, "Sign in to continue")
    async with session_factory()() as db:
        session = await db.scalar(
            select(AccessToken).where(
                AccessToken.token == token,
                AccessToken.created_at
                >= datetime.now(UTC) - timedelta(seconds=SESSION_LIFETIME_SECONDS),
            )
        )
        if session is None:
            raise HTTPException(401, "Session expired")
        user = await db.get(User, session.user_id)
        if user is None or not user.is_active:
            raise HTTPException(401, "Session is inactive")
        membership = await db.scalar(
            select(Membership).where(
                Membership.user_id == user.id, Membership.workspace_id == workspace_id
            )
        )
        if membership is None:
            raise HTTPException(404, "Workspace not found")
        return WorkspaceAccess(workspace_id, user.id, membership.role)
