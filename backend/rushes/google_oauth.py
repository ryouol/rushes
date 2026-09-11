"""Google's verified identity exchange; no provider access or refresh tokens are retained."""

import asyncio
import hashlib
import re
import secrets
import time
from base64 import urlsafe_b64encode
from types import SimpleNamespace
from urllib.parse import urlencode

import httpx
from google.oauth2.id_token import verify_oauth2_token
from pydantic import EmailStr, TypeAdapter

from rushes.config import settings

CERTIFICATES_URL = "https://www.googleapis.com/oauth2/v1/certs"
TOKEN_URL = "https://oauth2.googleapis.com/token"
_certificate_cache: tuple[float, bytes] | None = None
_certificate_lock = asyncio.Lock()


async def google_certificates(client: httpx.AsyncClient) -> bytes:
    global _certificate_cache
    if _certificate_cache and _certificate_cache[0] > time.monotonic():
        return _certificate_cache[1]
    async with _certificate_lock:
        if _certificate_cache and _certificate_cache[0] > time.monotonic():
            return _certificate_cache[1]
        response = await client.get(CERTIFICATES_URL)
        response.raise_for_status()
        policy = response.headers.get("cache-control", "").lower()
        max_age = re.search(r"(?:^|,)\s*max-age=(\d+)(?:\s*(?:,|$))", policy)
        try:
            age = max(0, int(response.headers.get("age", "0")))
        except ValueError:
            age = 3600
        ttl = max(0, min(3600, int(max_age[1]) - age)) if max_age else 0
        if "no-cache" in policy or "no-store" in policy:
            ttl = 0
        _certificate_cache = (time.monotonic() + ttl, response.content) if ttl else None
        return response.content


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def callback_url() -> str:
    return settings().origin + "/api/auth/google/callback"


def authorization_url(state: str, nonce: str, verifier: str) -> str:
    challenge = urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
        {
            "client_id": settings().google_client_id,
            "redirect_uri": callback_url(),
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
    )


async def exchange_identity(code: str, verifier: str, nonce: str) -> dict:
    config = settings()
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "client_id": config.google_client_id,
                "client_secret": config.google_client_secret.get_secret_value(),
                "redirect_uri": callback_url(),
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
            },
        )
        response.raise_for_status()
        token = response.json().get("id_token")
        if not isinstance(token, str) or not 1 <= len(token) <= 16384:
            raise ValueError("Invalid identity token")
        certificates = await google_certificates(client)

    # Fetch asynchronously, then give the official verifier the fixed Google certificate response.
    # This verifies signature, issuer, audience, issued-at and expiry without blocking network I/O.
    def certificate_request(url, method):
        if url != CERTIFICATES_URL or method != "GET":
            raise ValueError("Unexpected certificate request")
        return SimpleNamespace(status=200, data=certificates)

    claims = verify_oauth2_token(token, certificate_request, config.google_client_id)
    if claims.get("azp", config.google_client_id) != config.google_client_id:
        raise ValueError("Invalid authorized party")
    if not isinstance(claims.get("nonce"), str) or not secrets.compare_digest(
        claims["nonce"], nonce
    ):
        raise ValueError("Invalid nonce")
    if claims.get("email_verified") is not True:
        raise ValueError("Email is not verified")
    subject = claims.get("sub")
    if not isinstance(subject, str) or not 1 <= len(subject) <= 255 or not subject.isascii():
        raise ValueError("Invalid Google subject")
    email = str(TypeAdapter(EmailStr).validate_python(claims.get("email"))).lower()
    if len(email) > 320:
        raise ValueError("Invalid email")
    return {"subject": subject, "email": email, "name": str(claims.get("name") or "")[:120]}
