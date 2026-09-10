import time
from collections import defaultdict, deque
from ipaddress import ip_address

from starlette.responses import JSONResponse

from rushes.config import settings


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
        if scope["path"] in {"/api/auth/login", "/api/auth/register"} and unsafe:
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
