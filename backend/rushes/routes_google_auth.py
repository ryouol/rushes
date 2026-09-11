"""One-time server OAuth state, explicit identity linking, and existing RUSHES sessions."""

import asyncio
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from fastapi_users.password import PasswordHelper
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from rushes.auth import (
    SESSION_LIFETIME_SECONDS,
    current_user,
    database_strategy,
    lock_account_email,
    transport,
)
from rushes.config import settings
from rushes.db import get_session
from rushes.google_oauth import authorization_url, digest, exchange_identity
from rushes.models import AccessToken, GoogleIdentity, OAuthAttempt, User, now

router = APIRouter(prefix="/api/auth")
FLOW_COOKIE = "rushes_oauth_browser"
FLOW_PATH = "/api/auth/google"
FLOW_SECONDS = 600


def valid_destination(value: str) -> bool:
    if (
        not 1 <= len(value) <= 2048
        or "\\" in value
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        return False
    try:
        url = urlsplit(value)
    except ValueError:
        return False
    return (
        not url.scheme
        and not url.netloc
        and not url.fragment
        and (url.path == "/app" or value == "/onboarding")
        and not value.startswith("//")
    )


def flow_cookie(response: Response, value: str = "", *, clear=False):
    response.set_cookie(
        FLOW_COOKIE,
        value,
        max_age=0 if clear else FLOW_SECONDS,
        path=FLOW_PATH,
        secure=settings().origin.startswith("https:"),
        httponly=True,
        samesite="lax",
    )


def finish(path: str) -> RedirectResponse:
    response = RedirectResponse(path, status_code=303)
    flow_cookie(response, clear=True)
    return response


def failed(code: str, *, linking=False) -> RedirectResponse:
    if linking:
        result = "cancelled" if code == "google_cancelled" else "link_failed"
        return finish("/app?view=settings&google=" + result)
    return finish("/login?error=" + code)


async def begin(request: Request, db: AsyncSession, *, user: User | None = None):
    if not settings().google_configured:
        raise HTTPException(503, "Google sign-in is not configured for this deployment.")
    destination = request.query_params.get("next", "/app")
    if not valid_destination(destination) or len(request.query_params.getlist("next")) > 1:
        raise HTTPException(400, "Choose a RUSHES sign-in destination.")
    session_token = None
    if user:
        session_token = request.cookies.get(transport.cookie_name)
        active_token = await db.scalar(
            select(AccessToken.token)
            .where(
                AccessToken.token == session_token,
                AccessToken.user_id == user.id,
                AccessToken.created_at >= now() - timedelta(seconds=SESSION_LIFETIME_SECONDS),
            )
            .with_for_update()
        )
        if active_token is None:
            raise HTTPException(401, "Sign in again before connecting Google.")
        if await db.scalar(select(GoogleIdentity.subject).where(GoogleIdentity.user_id == user.id)):
            raise HTTPException(409, "A Google account is already connected.")
    # Bound anonymous state storage across processes, in addition to the per-client auth throttle.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended('rushes-oauth-start', 0))")
    )
    await db.execute(delete(OAuthAttempt).where(OAuthAttempt.expires_at <= now()))
    if await db.scalar(select(func.count()).select_from(OAuthAttempt)) >= 10000:
        raise HTTPException(429, "Sign-in is busy. Try again in a few minutes.")
    state, browser, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(4))
    db.add(
        OAuthAttempt(
            state_hash=digest(state),
            browser_hash=digest(browser),
            nonce=nonce,
            verifier=verifier,
            destination=destination,
            expires_at=now() + timedelta(seconds=FLOW_SECONDS),
            link_session_token=session_token,
        )
    )
    await db.commit()
    return authorization_url(state, nonce, verifier), browser


@router.get("/providers")
async def providers():
    return {"google": settings().google_configured}


@router.get("/google/account")
async def google_account(user: User = Depends(current_user), db=Depends(get_session)):
    email = await db.scalar(select(GoogleIdentity.email).where(GoogleIdentity.user_id == user.id))
    return {
        "available": settings().google_configured,
        "connected": email is not None,
        "email": email,
    }


@router.get("/google/authorize")
async def authorize(request: Request, db=Depends(get_session)):
    if not settings().google_configured:
        return failed("google_unavailable")
    url, browser = await begin(request, db)
    response = RedirectResponse(url, status_code=302)
    flow_cookie(response, browser)
    return response


@router.post("/google/link")
async def link(
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db=Depends(get_session),
):
    url, browser = await begin(request, db, user=user)
    flow_cookie(response, browser)
    return {"authorization_url": url}


async def resolve_user(db: AsyncSession, attempt: OAuthAttempt, identity: dict) -> User:
    await lock_account_email(db, identity["email"])
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": "rushes-google:subject:" + identity["subject"]},
    )
    linked = await db.get(GoogleIdentity, identity["subject"])
    if attempt.link_session_token:
        user = await db.scalar(
            select(User)
            .join(AccessToken, AccessToken.user_id == User.id)
            .where(
                AccessToken.token == attempt.link_session_token,
                AccessToken.created_at >= now() - timedelta(seconds=SESSION_LIFETIME_SECONDS),
                User.is_active.is_(True),
            )
            .with_for_update()
        )
        if user is None or (linked and linked.user_id != user.id):
            raise ValueError("Link session or identity is unavailable")
        current = await db.scalar(select(GoogleIdentity).where(GoogleIdentity.user_id == user.id))
        if current and current.subject != identity["subject"]:
            raise ValueError("Another Google account is already linked")
    elif linked:
        user = await db.get(User, linked.user_id)
        if not user or not user.is_active:
            raise ValueError("Account is unavailable")
    else:
        if await db.scalar(select(User.id).where(func.lower(User.email) == identity["email"])):
            raise LinkRequired()
        user = User(
            email=identity["email"],
            name=identity["name"],
            is_verified=True,
            hashed_password=await asyncio.to_thread(
                PasswordHelper().hash, secrets.token_urlsafe(48)
            ),
        )
        db.add(user)
        await db.flush()
    if linked:
        linked.email = identity["email"]
    else:
        db.add(
            GoogleIdentity(subject=identity["subject"], user_id=user.id, email=identity["email"])
        )
    await db.flush()
    return user


class LinkRequired(ValueError):
    pass


@router.get("/google/callback")
async def callback(request: Request, db=Depends(get_session), strategy=Depends(database_strategy)):
    query = request.query_params
    state, browser = query.get("state", ""), request.cookies.get(FLOW_COOKIE, "")
    if (
        not 16 <= len(state) <= 128
        or not 16 <= len(browser) <= 128
        or any(len(query.getlist(key)) > 1 for key in ("state", "code", "error"))
    ):
        return failed("google_invalid")
    attempt = await db.scalar(
        delete(OAuthAttempt)
        .where(
            OAuthAttempt.state_hash == digest(state),
            OAuthAttempt.browser_hash == digest(browser),
            OAuthAttempt.expires_at > now(),
        )
        .returning(OAuthAttempt)
    )
    await db.commit()  # Consume before any provider request: a failed exchange is never replayable.
    if attempt is None:
        return failed("google_invalid")
    linking = attempt.link_session_token is not None
    if not settings().google_configured:
        return failed("google_unavailable", linking=linking)
    if query.get("error"):
        code = "google_cancelled" if query["error"] == "access_denied" else "google_failed"
        return failed(code, linking=linking)
    code = query.get("code", "")
    if not 1 <= len(code) <= 4096:
        return failed("google_invalid", linking=linking)
    try:
        identity = await exchange_identity(code, attempt.verifier, attempt.nonce)
        user = await resolve_user(db, attempt, identity)
        # Same strategy and cookie transport as password sign-in; commit identity + session together.
        token = await strategy.write_token(user)
    except LinkRequired:
        await db.rollback()
        return failed("google_link_required", linking=linking)
    except IntegrityError:
        await db.rollback()
        return failed("google_failed", linking=linking)
    except Exception:
        # Provider exceptions can contain codes, tokens or secrets. Never echo or log their values.
        await db.rollback()
        return failed("google_failed", linking=linking)
    response = finish("/app?view=settings&google=linked" if linking else attempt.destination)
    login_response = await transport.get_login_response(token)
    response.raw_headers.extend(
        header for header in login_response.raw_headers if header[0].lower() == b"set-cookie"
    )
    return response
