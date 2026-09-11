import asyncio
import json
import secrets
import time
import uuid
from base64 import urlsafe_b64encode
from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from google.auth import crypt, jwt
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from rushes import auth, google_oauth, routes_google_auth
from rushes.api import app
from rushes.auth import transport
from rushes.config import settings
from rushes.db import session_factory
from rushes.models import TENANT_TABLES, AccessToken, GoogleIdentity, OAuthAttempt, User, now
from rushes.routes_google_auth import FLOW_COOKIE, valid_destination
from sqlalchemy import func, select


@pytest.fixture(scope="module")
def signing_key():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return crypt.RSASigner.from_string(private, key_id="fixture"), public.decode()


def api_client():
    return AsyncClient(
        transport=ASGITransport(
            app=app, client=(f"127.1.{secrets.randbelow(255)}.{secrets.randbelow(255)}", 1)
        ),
        base_url="http://localhost",
        headers={"Origin": settings().origin},
    )


@pytest.fixture
async def oauth(monkeypatch, signing_key):
    monkeypatch.setattr(google_oauth, "_certificate_cache", None)
    monkeypatch.setattr(google_oauth, "_certificate_lock", asyncio.Lock())
    monkeypatch.setattr(settings(), "google_client_id", "rushes-test.apps.googleusercontent.com")
    monkeypatch.setattr(settings(), "google_client_secret", SecretStr("fixture-client-secret"))
    monkeypatch.setattr(settings(), "client_ip_header", None)
    signer, public = signing_key
    state = {
        "claims": {
            "iss": "https://accounts.google.com",
            "aud": settings().google_client_id,
            "sub": "fixture-" + str(uuid.uuid4()),
            "email": f"google-{uuid.uuid4()}@example.com",
            "email_verified": True,
            "name": "Google fixture",
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,
        },
        "calls": [],
        "failure": None,
        "exchanges": {},
        "token_gate": None,
    }

    async def provider(request):
        state["calls"].append(request)
        if request.url == google_oauth.TOKEN_URL:
            form = parse_qs(request.content.decode())
            exchange = state["exchanges"].get(form["code"][0], state)
            claims = exchange["claims"]
            assert form["code_verifier"] == [exchange["verifier"]]
            assert form["client_id"] == [settings().google_client_id]
            assert form["redirect_uri"] == [settings().origin + "/api/auth/google/callback"]
            if state["token_gate"]:
                await asyncio.wait_for(state["token_gate"](), timeout=5)
            if state["failure"] == "timeout":
                raise httpx.ReadTimeout("sensitive-provider-detail", request=request)
            if state["failure"] == "rejected":
                return httpx.Response(400, json={"error": "sensitive-provider-detail"})
            token = jwt.encode(signer, claims).decode()
            if state["failure"] == "signature":
                header, _, signature = token.split(".")
                payload = (
                    urlsafe_b64encode(json.dumps({**claims, "name": "forged"}).encode())
                    .decode()
                    .rstrip("=")
                )
                token = ".".join([header, payload, signature])
            return httpx.Response(200, json={"id_token": token, "access_token": "not-retained"})
        assert request.url == google_oauth.CERTIFICATES_URL
        return httpx.Response(200, json={"fixture": public})

    real_client = AsyncClient
    monkeypatch.setattr(
        google_oauth.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(provider)),
    )
    async with api_client() as client:
        state["client"] = client
        yield state


async def start(oauth, *, link=False, destination="/app", code=None):
    client = oauth["client"]
    response = (
        await client.post("/api/auth/google/link")
        if link
        else await client.get("/api/auth/google/authorize", params={"next": destination})
    )
    assert response.status_code == (200 if link else 302)
    url = response.json()["authorization_url"] if link else response.headers["location"]
    query = parse_qs(urlsplit(url).query)
    oauth["claims"]["nonce"] = query["nonce"][0]
    async with session_factory()() as db:
        attempt = await db.get(OAuthAttempt, google_oauth.digest(query["state"][0]))
        oauth["verifier"] = attempt.verifier
    if code is not None:
        oauth["exchanges"][code] = {
            "claims": dict(oauth["claims"]),
            "verifier": oauth["verifier"],
        }
    return query, response


async def complete(oauth, query, **params):
    return await oauth["client"].get(
        "/api/auth/google/callback",
        params={
            "state": query["state"][0],
            "code": "fixture-authorization-code",
            **params,
        },
    )


async def password_user(oauth):
    async with session_factory()() as db:
        user = User(
            email=oauth["claims"]["email"],
            name="Existing local account",
            hashed_password="unusable-fixture-password",
        )
        db.add(user)
        await db.flush()
        token = secrets.token_urlsafe(32)
        db.add(AccessToken(token=token, user_id=user.id))
        await db.commit()
    return user, token


async def test_google_signup_uses_pkce_verified_identity_and_existing_private_session(oauth):
    query, response = await start(oauth, destination="/onboarding")
    assert urlsplit(response.headers["location"]).netloc == "accounts.google.com"
    assert query["scope"] == ["openid email profile"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"] == [
        urlsafe_b64encode(bytes.fromhex(google_oauth.digest(oauth["verifier"])))
        .decode()
        .rstrip("=")
    ]
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Max-Age=600" in cookie
    response = await complete(oauth, query)
    assert response.status_code == 303 and response.headers["location"] == "/onboarding"
    assert len(response.headers.get_list("set-cookie")) == 2
    me = (await oauth["client"].get("/api/auth/me")).json()
    assert me["is_verified"] and me["email"] == oauth["claims"]["email"]
    assert (await oauth["client"].get("/api/workspaces")).json() == []
    async with session_factory()() as db:
        identity = await db.get(GoogleIdentity, oauth["claims"]["sub"])
        assert str(identity.user_id) == me["id"]
        assert await db.get(OAuthAttempt, google_oauth.digest(query["state"][0])) is None
    assert (await complete(oauth, query)).headers["location"] == "/login?error=google_invalid"
    assert len(oauth["calls"]) == 2


@pytest.mark.parametrize(
    "invalid",
    [
        "aud",
        "iss",
        "nonce",
        "azp",
        "expired",
        "unverified",
        "subject",
        "email",
        "signature",
        "timeout",
        "rejected",
    ],
)
async def test_rejects_invalid_signed_claims_and_provider_failures(oauth, invalid):
    query, _ = await start(oauth)
    if invalid in {"aud", "iss", "nonce", "azp"}:
        oauth["claims"][invalid] = "wrong-value"
    elif invalid == "expired":
        oauth["claims"]["exp"] = int(time.time()) - 100
    elif invalid == "unverified":
        oauth["claims"]["email_verified"] = "true"
    elif invalid == "subject":
        oauth["claims"]["sub"] = ""
    elif invalid == "email":
        oauth["claims"]["email"] = "invalid-email"
    else:
        oauth["failure"] = invalid
    response = await complete(oauth, query)
    assert response.headers["location"] == "/login?error=google_failed"
    assert "sensitive-provider-detail" not in response.text
    assert (await oauth["client"].get("/api/auth/me")).status_code == 401
    async with session_factory()() as db:
        assert await db.get(GoogleIdentity, oauth["claims"]["sub"]) is None


async def test_callback_browser_binding_expiry_cancellation_and_one_time_use(oauth):
    query, _ = await start(oauth)
    browser = oauth["client"].cookies.get(FLOW_COOKIE)
    oauth["client"].cookies.clear()
    assert (await complete(oauth, query)).headers["location"].endswith("google_invalid")
    assert not oauth["calls"]
    oauth["client"].cookies.set(FLOW_COOKIE, browser)
    canceled = await complete(oauth, query, error="access_denied")
    assert canceled.headers["location"] == "/login?error=google_cancelled"
    assert not oauth["calls"]
    query, _ = await start(oauth)
    async with session_factory()() as db:
        attempt = await db.get(OAuthAttempt, google_oauth.digest(query["state"][0]))
        attempt.expires_at = now() - timedelta(seconds=1)
        await db.commit()
    assert (await complete(oauth, query)).headers["location"].endswith("google_invalid")


async def test_existing_email_requires_authenticated_explicit_link(oauth):
    user, token = await password_user(oauth)
    query, _ = await start(oauth)
    assert (await complete(oauth, query)).headers["location"] == "/login?error=google_link_required"
    assert (await oauth["client"].post("/api/auth/google/link")).status_code == 401
    oauth["client"].cookies.set(transport.cookie_name, token)
    query, _ = await start(oauth, link=True)
    # Strict session cookies are absent on Google's cross-site callback. The temporary
    # Lax cookie binds linking to the initiating session, which must still exist.
    oauth["client"].cookies.delete(transport.cookie_name)
    assert (await complete(oauth, query)).headers["location"] == "/app?view=settings&google=linked"
    assert (await oauth["client"].get("/api/auth/me")).json()["id"] == str(user.id)
    assert (await oauth["client"].get("/api/auth/google/account")).json() == {
        "available": True,
        "connected": True,
        "email": oauth["claims"]["email"],
    }
    assert (await oauth["client"].post("/api/auth/google/link")).status_code == 409


async def test_logged_out_or_expired_link_session_cannot_connect(oauth):
    _, token = await password_user(oauth)
    oauth["client"].cookies.set(transport.cookie_name, token)
    query, _ = await start(oauth, link=True)
    await oauth["client"].post("/api/auth/logout")
    assert (await complete(oauth, query)).headers["location"].endswith("google_invalid")
    assert not oauth["calls"]
    async with session_factory()() as db:
        assert await db.get(OAuthAttempt, google_oauth.digest(query["state"][0])) is None


async def test_link_session_expiry_is_rechecked_after_provider_return(oauth):
    _, token = await password_user(oauth)
    oauth["client"].cookies.set(transport.cookie_name, token)
    query, _ = await start(oauth, link=True)
    async with session_factory()() as db:
        session = await db.get(AccessToken, token)
        session.created_at = now() - timedelta(days=8)
        await db.commit()
    response = await complete(oauth, query)
    assert response.headers["location"] == "/app?view=settings&google=link_failed"
    async with session_factory()() as db:
        assert await db.get(GoogleIdentity, oauth["claims"]["sub"]) is None


async def test_google_identity_cannot_be_moved_to_another_account(oauth):
    query, _ = await start(oauth)
    await complete(oauth, query)
    original = (await oauth["client"].get("/api/auth/me")).json()["id"]
    await oauth["client"].post("/api/auth/logout")
    oauth["claims"]["email"] = f"separate-{uuid.uuid4()}@example.com"
    other, token = await password_user(oauth)
    oauth["client"].cookies.clear()
    oauth["client"].cookies.set(transport.cookie_name, token)
    query, _ = await start(oauth, link=True)
    assert (await complete(oauth, query)).headers[
        "location"
    ] == "/app?view=settings&google=link_failed"
    assert (await oauth["client"].get("/api/auth/me")).json()["id"] == str(other.id)
    async with session_factory()() as db:
        identity = await db.get(GoogleIdentity, oauth["claims"]["sub"])
        assert str(identity.user_id) == original


async def test_inactive_google_account_does_not_receive_new_session(oauth):
    query, _ = await start(oauth)
    await complete(oauth, query)
    user_id = uuid.UUID((await oauth["client"].get("/api/auth/me")).json()["id"])
    await oauth["client"].post("/api/auth/logout")
    async with session_factory()() as db:
        user = await db.get(User, user_id)
        user.is_active = False
        await db.commit()
    query, _ = await start(oauth)
    assert (await complete(oauth, query)).headers["location"].endswith("google_failed")
    assert (await oauth["client"].get("/api/auth/me")).status_code == 401


async def test_existing_google_subject_signs_into_same_account_without_email_relinking(oauth):
    query, _ = await start(oauth)
    await complete(oauth, query)
    first_user = (await oauth["client"].get("/api/auth/me")).json()["id"]
    await oauth["client"].post("/api/auth/logout")
    oauth["claims"]["email"] = f"changed-{uuid.uuid4()}@example.com"
    query, _ = await start(oauth)
    assert (await complete(oauth, query)).headers["location"] == "/app"
    assert (await oauth["client"].get("/api/auth/me")).json()["id"] == first_user
    async with session_factory()() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(GoogleIdentity)
                .where(GoogleIdentity.subject == oauth["claims"]["sub"])
            )
            == 1
        )


async def test_atomic_callback_consumption_allows_only_one_exchange(oauth):
    query, _ = await start(oauth)
    responses = await asyncio.gather(complete(oauth, query), complete(oauth, query))
    assert sorted(response.headers["location"] for response in responses) == [
        "/app",
        "/login?error=google_invalid",
    ]
    assert len(oauth["calls"]) == 2


@pytest.mark.parametrize("same_subject", [True, False], ids=["same-subject", "same-email"])
async def test_distinct_callbacks_serialize_matching_accounts(oauth, same_subject):
    async with api_client() as other_client:
        other = {**oauth, "client": other_client, "claims": dict(oauth["claims"])}
        if not same_subject:
            other["claims"]["sub"] = "other-" + str(uuid.uuid4())
        first, _ = await start(oauth, code="first")
        second, _ = await start(other, code="second")
        assert first["state"] != second["state"]
        assert oauth["client"].cookies.get(FLOW_COOKIE) != other_client.cookies.get(FLOW_COOKIE)
        oauth["token_gate"] = asyncio.Barrier(2).wait

        responses = await asyncio.wait_for(
            asyncio.gather(
                complete(oauth, first, code="first"), complete(other, second, code="second")
            ),
            timeout=10,
        )
        expected = ["/app", "/app" if same_subject else "/login?error=google_link_required"]
        assert sorted(response.headers["location"] for response in responses) == sorted(expected)
        async with session_factory()() as db:
            users = list(
                await db.scalars(
                    select(User).where(func.lower(User.email) == oauth["claims"]["email"])
                )
            )
            assert len(users) == 1
            identities = list(
                await db.scalars(
                    select(GoogleIdentity).where(GoogleIdentity.user_id == users[0].id)
                )
            )
            assert len(identities) == 1
            assert identities[0].subject in {oauth["claims"]["sub"], other["claims"]["sub"]}
            assert await db.scalar(
                select(func.count())
                .select_from(AccessToken)
                .where(AccessToken.user_id == users[0].id)
            ) == (2 if same_subject else 1)
            for query in (first, second):
                assert await db.get(OAuthAttempt, google_oauth.digest(query["state"][0])) is None
        for client, response in zip((oauth["client"], other_client), responses, strict=True):
            me = await client.get("/api/auth/me")
            if response.headers["location"] == "/app":
                assert me.status_code == 200 and me.json()["id"] == str(users[0].id)
            else:
                assert me.status_code == 401


async def test_concurrent_subjects_cannot_both_link_to_one_account(oauth):
    user, first_token = await password_user(oauth)
    second_token = secrets.token_urlsafe(32)
    async with session_factory()() as db:
        db.add(AccessToken(token=second_token, user_id=user.id))
        await db.commit()
    oauth["client"].cookies.set(transport.cookie_name, first_token)
    async with api_client() as other_client:
        other_client.cookies.set(transport.cookie_name, second_token)
        other = {
            **oauth,
            "client": other_client,
            "claims": {
                **oauth["claims"],
                "sub": "other-" + str(uuid.uuid4()),
                "email": f"other-{uuid.uuid4()}@example.com",
            },
        }
        first, _ = await start(oauth, link=True, code="first")
        second, _ = await start(other, link=True, code="second")
        oauth["token_gate"] = asyncio.Barrier(2).wait
        responses = await asyncio.wait_for(
            asyncio.gather(
                complete(oauth, first, code="first"), complete(other, second, code="second")
            ),
            timeout=10,
        )
        assert sorted(response.headers["location"] for response in responses) == [
            "/app?view=settings&google=link_failed",
            "/app?view=settings&google=linked",
        ]
        winner = next(
            browser
            for browser, response in zip((oauth, other), responses, strict=True)
            if response.headers["location"].endswith("google=linked")
        )
        async with session_factory()() as db:
            identities = list(
                await db.scalars(select(GoogleIdentity).where(GoogleIdentity.user_id == user.id))
            )
            assert len(identities) == 1
            assert identities[0].subject == winner["claims"]["sub"]
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(AccessToken)
                    .where(AccessToken.user_id == user.id)
                )
                == 3
            )
            assert (await db.get(User, user.id)).hashed_password == user.hashed_password
        for client in (oauth["client"], other_client):
            assert (await client.get("/api/auth/me")).json()["id"] == str(user.id)


async def test_logout_during_provider_exchange_prevents_link_and_replacement_session(oauth):
    user, token = await password_user(oauth)
    oauth["client"].cookies.set(transport.cookie_name, token)
    query, _ = await start(oauth, link=True)
    exchanging, released = asyncio.Event(), asyncio.Event()

    async def suspend_exchange():
        exchanging.set()
        await released.wait()

    oauth["token_gate"] = suspend_exchange
    callback_task = asyncio.create_task(complete(oauth, query))
    try:
        await asyncio.wait_for(exchanging.wait(), timeout=5)
        async with session_factory()() as db:
            assert await db.get(OAuthAttempt, google_oauth.digest(query["state"][0])) is None
        assert (await oauth["client"].post("/api/auth/logout")).status_code == 204
    finally:
        released.set()
        response = await asyncio.wait_for(callback_task, timeout=10)
    assert response.headers["location"] == "/app?view=settings&google=link_failed"
    assert not any(
        cookie.startswith(transport.cookie_name + "=")
        for cookie in response.headers.get_list("set-cookie")
    )
    assert (await oauth["client"].get("/api/auth/me")).status_code == 401
    async with session_factory()() as db:
        assert await db.get(GoogleIdentity, oauth["claims"]["sub"]) is None
        assert (
            await db.scalar(
                select(func.count()).select_from(AccessToken).where(AccessToken.user_id == user.id)
            )
            == 0
        )


async def test_google_and_mixed_case_password_signup_share_one_account(oauth, monkeypatch):
    query, _ = await start(oauth)
    hashing, released, registering = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def suspend_hash(function, *args):
        hashing.set()
        await released.wait()
        return await asyncio.to_thread(function, *args)

    monkeypatch.setattr(routes_google_auth, "asyncio", SimpleNamespace(to_thread=suspend_hash))
    callback_task = asyncio.create_task(complete(oauth, query))
    registration_task = None
    async with api_client() as other_client:
        try:
            await asyncio.wait_for(hashing.wait(), timeout=5)
            lock_account_email = auth.lock_account_email

            async def observe_registration(db, email):
                registering.set()
                await lock_account_email(db, email)

            monkeypatch.setattr(auth, "lock_account_email", observe_registration)
            registration_task = asyncio.create_task(
                other_client.post(
                    "/api/auth/register",
                    json={
                        "email": oauth["claims"]["email"].upper(),
                        "password": "synthetic-password-only",
                        "name": "Concurrent password signup",
                    },
                )
            )
            await asyncio.wait_for(registering.wait(), timeout=5)
            assert not registration_task.done()
        finally:
            released.set()
            response = await asyncio.wait_for(callback_task, timeout=10)
            if registration_task is not None:
                registration = await asyncio.wait_for(registration_task, timeout=10)
        assert response.headers["location"] == "/app"
        assert registration.status_code == 400
        assert registration.json()["detail"] == "REGISTER_USER_ALREADY_EXISTS"
        assert (await other_client.get("/api/auth/me")).status_code == 401
    me = (await oauth["client"].get("/api/auth/me")).json()
    async with session_factory()() as db:
        users = list(
            await db.scalars(select(User).where(func.lower(User.email) == oauth["claims"]["email"]))
        )
        assert len(users) == 1 and str(users[0].id) == me["id"]
        assert (await db.get(GoogleIdentity, oauth["claims"]["sub"])).user_id == users[0].id


async def test_configuration_redirect_allowlist_and_origin_boundary(oauth, monkeypatch):
    client = oauth["client"]
    assert (await client.get("/api/auth/providers")).json() == {"google": True}
    for destination in [
        "https://evil.example",
        "//evil.example",
        "/app#fragment",
        "/\\evil.example",
    ]:
        assert (
            await client.get("/api/auth/google/authorize", params={"next": destination})
        ).status_code == 400
    assert (
        await client.post("/api/auth/google/link", headers={"Origin": "https://evil.example"})
    ).status_code == 403
    assert (await client.get("/api/auth/google/account")).status_code == 401
    monkeypatch.setattr(settings(), "google_client_secret", None)
    assert (await client.get("/api/auth/providers")).json() == {"google": False}
    assert (await client.get("/api/auth/google/authorize")).headers[
        "location"
    ] == "/login?error=google_unavailable"
    assert not oauth["calls"]


def test_authentication_tables_are_not_tenant_tables():
    assert "google_identity" not in TENANT_TABLES and "oauth_attempt" not in TENANT_TABLES


@pytest.mark.parametrize(
    "destination",
    [
        "/app",
        "/app?workspace=fixture&project=fixture",
        "/app?view=settings",
        "/onboarding",
    ],
)
async def test_safe_application_destination_roundtrip(oauth, destination):
    query, _ = await start(oauth, destination=destination)
    assert (await complete(oauth, query)).headers["location"] == destination


@pytest.mark.parametrize(
    "destination",
    [
        "https://evil.example/app",
        "http://[",
        "//evil.example/app",
        "///app",
        "/\\evil.example/app",
        "/app\n",
        "/app#fragment",
        "/app/../elsewhere",
        "/%61pp",
        "/onboarding?next=evil",
        "/app?" + "x" * 2048,
    ],
)
def test_rejects_unsafe_destination(destination):
    assert not valid_destination(destination)


async def test_callback_duplicate_state_is_rejected_without_provider_call(oauth):
    query, _ = await start(oauth)
    response = await oauth["client"].get(
        "/api/auth/google/callback",
        params=[
            ("state", query["state"][0]),
            ("state", query["state"][0]),
            ("code", "fixture-code"),
        ],
    )
    assert response.headers["location"].endswith("google_invalid")
    assert not oauth["calls"]


async def test_oauth_throttle_applies_to_navigation_requests(oauth):
    for _ in range(10):
        assert (await oauth["client"].get("/api/auth/google/authorize")).status_code == 302
    assert (await oauth["client"].get("/api/auth/google/authorize")).status_code == 429


async def test_callback_query_is_available_to_handler_but_absent_from_access_log(oauth):
    query, _ = await start(oauth)
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/auth/google/callback",
        "root_path": "",
        "query_string": f"state={query['state'][0]}&error=access_denied".encode(),
        "headers": [
            (b"host", b"localhost"),
            (b"cookie", f"{FLOW_COOKIE}={oauth['client'].cookies.get(FLOW_COOKIE)}".encode()),
        ],
        "client": ("127.2.1.1", 1),
        "server": ("localhost", 80),
    }
    messages = []

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        if message["type"] == "http.response.start":
            assert scope["query_string"] == b""
        messages.append(message)

    await app(scope, receive, send)
    assert dict(messages[0]["headers"])[b"location"] == b"/login?error=google_cancelled"


@pytest.mark.parametrize(
    "rejection,expected", [("host", 400), ("origin", 403), ("ingress", 503), ("rate", 429)]
)
async def test_callback_query_not_logged_on_early_rejection(monkeypatch, rejection, expected):
    from rushes.security import CallbackLogBoundary, OriginBoundary
    from starlette.middleware.trustedhost import TrustedHostMiddleware

    async def endpoint(scope, receive, send):
        raise AssertionError("Rejected callback must not reach endpoint")

    boundary = OriginBoundary(endpoint)
    if rejection == "rate":
        boundary.auth_attempts["127.0.0.1"].extend([time.monotonic()] * 10)
    monkeypatch.setattr(
        settings(), "client_ip_header", "x-forwarded-for" if rejection == "ingress" else None
    )
    application = CallbackLogBoundary(TrustedHostMiddleware(boundary, allowed_hosts=["localhost"]))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/auth/google/callback",
        "query_string": b"code=never-log-this&state=private-state",
        "client": ("127.0.0.1", 1),
        "headers": [(b"host", b"foreign.example" if rejection == "host" else b"localhost")],
    }
    if rejection == "origin":
        scope["headers"].append((b"origin", b"https://foreign.example"))
    messages = []

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        assert scope["query_string"] == b""
        messages.append(message)

    await application(scope, receive, send)
    assert messages[0]["status"] == expected


async def test_certificate_cache_honors_expiry_and_coalesces_requests(monkeypatch):
    monkeypatch.setattr(google_oauth, "_certificate_cache", None)
    monkeypatch.setattr(google_oauth, "_certificate_lock", asyncio.Lock())
    clock = [100.0]
    monkeypatch.setattr(google_oauth.time, "monotonic", lambda: clock[0])
    requests = []

    async def respond(request):
        requests.append(request)
        await asyncio.sleep(0)
        return httpx.Response(
            200,
            content=b"public-certificates",
            headers={"cache-control": "public, max-age=120", "age": "20"},
        )

    async with AsyncClient(transport=httpx.MockTransport(respond)) as client:
        results = await asyncio.gather(
            *(google_oauth.google_certificates(client) for _ in range(5))
        )
        assert results == [b"public-certificates"] * 5
        assert len(requests) == 1
        clock[0] = 199.0
        await google_oauth.google_certificates(client)
        assert len(requests) == 1
        clock[0] = 201.0
        await google_oauth.google_certificates(client)
        assert len(requests) == 2


@pytest.mark.parametrize("policy", ["no-store, max-age=120", "no-cache, max-age=120", ""])
async def test_certificate_cache_respects_no_cache(monkeypatch, policy):
    monkeypatch.setattr(google_oauth, "_certificate_cache", None)
    monkeypatch.setattr(google_oauth, "_certificate_lock", asyncio.Lock())
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200, content=b"public-certificates", headers={"cache-control": policy}
        )

    async with AsyncClient(transport=httpx.MockTransport(respond)) as client:
        await google_oauth.google_certificates(client)
        await google_oauth.google_certificates(client)
    assert len(requests) == 2
