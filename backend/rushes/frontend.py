"""Public HTTP boundary shared by exported pages and the application API."""

from ipaddress import ip_address
from pathlib import Path
from urllib.parse import quote, urlsplit

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.staticfiles import StaticFiles

SECURITY_HEADERS = {
    b"x-content-type-options": b"nosniff",
    b"x-frame-options": b"DENY",
    b"referrer-policy": b"same-origin",
    b"permissions-policy": b"camera=(), microphone=(), geolocation=()",
}
API_HEADERS = {b"cookie", b"content-type", b"content-length", b"range", b"origin", b"last-event-id"}
API_METHODS = {"DELETE", "GET", "HEAD", "PATCH", "POST", "PUT"}


class Frontend:
    def __init__(self, api, *, origin: str, client_ip_header: str = "", root: Path | None = None):
        self.api = api
        self.host = urlsplit(origin).netloc.lower()
        self.client_ip_header = client_ip_header.encode()
        self.files = StaticFiles(directory=root, html=True) if root is not None else None
        # Next's exported page and its navigation payload directory share a basename.
        self.pages = {"/" + page.stem: page.name for page in root.glob("*.html")} if root else {}

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return await self.api(scope, receive, send)
        if scope["type"] != "http":
            return await send({"type": "websocket.close", "code": 1000})

        async def secured_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() not in SECURITY_HEADERS
                ] + list(SECURITY_HEADERS.items())
                if message["status"] >= 400:
                    message["headers"] = [
                        (key, value) for key, value in message["headers"] if key != b"cache-control"
                    ] + [(b"cache-control", b"no-store")]
            await send(message)

        headers = dict(scope["headers"])
        path = scope["path"]
        if headers.get(b"host", b"").decode("latin1").lower() != self.host or path.startswith("//"):
            return await JSONResponse({"detail": "Request host or path is not allowed"}, 400)(
                scope, receive, secured_send
            )
        if path != "/" and path.endswith("/"):
            location = quote(path.rstrip("/"), safe="/!$&'()*+,-.:;=@_~")
            if scope["query_string"]:
                location += "?" + scope["query_string"].decode("latin1")
            return await RedirectResponse(location, 308)(scope, receive, secured_send)
        if path == "/api" or path.startswith("/api/"):
            if scope["method"] == "OPTIONS":
                return await Response(
                    status_code=204, headers={"Allow": ", ".join(sorted(API_METHODS | {"OPTIONS"}))}
                )(scope, receive, secured_send)
            if scope["method"] not in API_METHODS:
                return await JSONResponse({"detail": "Method not allowed"}, 405)(
                    scope, receive, secured_send
                )
            forwarded = [(key, value) for key, value in scope["headers"] if key in API_HEADERS]
            if self.client_ip_header:
                try:
                    address = ip_address(headers.get(self.client_ip_header, b"").decode("ascii"))
                    forwarded.append((b"x-rushes-client-ip", str(address).encode()))
                except (ValueError, UnicodeDecodeError):
                    pass
            forwarded.append((b"host", b"127.0.0.1:8741"))
            private_scope = {
                **scope,
                "headers": forwarded,
                "client": ("127.0.0.1", 0),
                "server": ("127.0.0.1", 8741),
                "scheme": "http",
            }
            return await self.api(private_scope, receive, secured_send)
        if self.files is None:
            return await JSONResponse({"detail": "Not found"}, 404)(scope, receive, secured_send)
        static_scope = {**scope, "path": "/" + self.pages[path]} if path in self.pages else scope
        try:
            response = await self.files.get_response(self.files.get_path(static_scope), static_scope)
        except HTTPException as error:
            response = JSONResponse({"detail": "Static resource unavailable"}, error.status_code)
        if path in {"/opengraph-image", "/twitter-image"} and response.status_code == 200:
            response.headers["content-type"] = "image/png"
        if response.status_code >= 400:
            # FileResponse otherwise turns a ranged request for 404.html into a 206.
            static_scope = {
                **static_scope,
                "headers": [(k, v) for k, v in static_scope["headers"] if k not in {b"range", b"if-range"}],
            }
        else:
            response.headers["cache-control"] = (
                "public, max-age=31536000, immutable"
                if path.startswith("/_next/static/")
                else "public, max-age=0, must-revalidate"
            )
        return await response(static_scope, receive, secured_send)
