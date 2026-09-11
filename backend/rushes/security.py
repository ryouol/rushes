import re
import time
from collections import defaultdict, deque
from ipaddress import ip_address

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from rushes.config import settings

MAX_REQUEST_BYTES = 64 * 1024
# Indexing accepts 200 paths; allow long filesystem paths even with JSON escaping.
MAX_INDEX_REQUEST_BYTES = 8 * 1024 * 1024
PROJECT_BODY_ROUTE = re.compile(r"/api/workspaces/[^/]+/projects/[^/]+/(upload|index)/?")


class CallbackLogBoundary:
    """Give the app callback parameters without leaving them in the server's access-log scope."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].rstrip("/") == "/api/auth/google/callback":
            application_scope = dict(scope)
            scope["query_string"] = b""
            return await self.app(application_scope, receive, send)
        return await self.app(scope, receive, send)


class RequestBodyBoundary:
    """Bound bytes before JSON/form parsing; media uploads enforce their own streaming limit."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = MAX_REQUEST_BYTES
        route = PROJECT_BODY_ROUTE.fullmatch(scope["path"])
        if scope["method"] == "POST" and route:
            if route[1] == "upload":
                return await self.app(scope, receive, send)
            limit = MAX_INDEX_REQUEST_BYTES
        detail = "Request body is too large. Shorten the input or split the import batch."
        length = dict(scope["headers"]).get(b"content-length")
        if length is not None:
            try:
                declared = int(length)
                if declared < 0:
                    raise ValueError
            except ValueError:
                return await JSONResponse({"detail": "Invalid Content-Length"}, 400)(
                    scope, receive, send
                )
            if declared > limit:
                return await JSONResponse({"detail": detail}, 413)(scope, receive, send)
        received = 0

        async def bounded_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # Starlette handles this before the endpoint can act or echo validation input.
                    raise HTTPException(413, detail)
            return message

        await self.app(scope, bounded_receive, send)


class OriginBoundary:
    def __init__(self, app):
        self.app = app
        self.auth_attempts = defaultdict(deque)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        origin = headers.get(b"origin", b"").decode()
        unsafe = scope["method"] not in {"GET", "HEAD", "OPTIONS"}
        if (origin and origin != settings().origin) or (unsafe and not origin):
            return await JSONResponse({"detail": "Request origin is not allowed"}, 403)(
                scope, receive, send
            )
        auth_route = (scope["path"] in {"/api/auth/login", "/api/auth/register"} and unsafe) or (
            scope["path"]
            in {"/api/auth/google/authorize", "/api/auth/google/callback", "/api/auth/google/link"}
        )
        if auth_route:
            address = scope.get("client", ("local", 0))[0]
            if settings().client_ip_header:
                try:
                    if not ip_address(address).is_loopback:
                        raise ValueError("Only the private web proxy can assert client identity")
                    address = str(ip_address(headers.get(b"x-rushes-client-ip", b"").decode()))
                except ValueError:
                    return await JSONResponse(
                        {"detail": "Trusted ingress client identity is unavailable"}, 503
                    )(scope, receive, send)
            now = time.monotonic()
            if len(self.auth_attempts) >= 4096 and address not in self.auth_attempts:
                expired = [
                    key
                    for key, values in self.auth_attempts.items()
                    if not values or now - values[-1] > 60
                ]
                for key in expired:
                    del self.auth_attempts[key]
                if len(self.auth_attempts) >= 4096:
                    address = "overflow"
            attempts = self.auth_attempts[address]
            while attempts and now - attempts[0] > 60:
                attempts.popleft()
            if len(attempts) >= 10:
                return await JSONResponse(
                    {"detail": "Too many attempts. Try again in a minute."}, 429
                )(scope, receive, send)
            attempts.append(now)

        async def secured_send(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"cache-control", b"no-store"),
                        (b"referrer-policy", b"same-origin"),
                        (b"cross-origin-resource-policy", b"same-origin"),
                    ]
                )
            await send(message)

        await self.app(scope, receive, secured_send)
