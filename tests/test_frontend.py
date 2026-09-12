import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from rushes.config import settings
from rushes.frontend import Frontend
from rushes.security import CallbackLogBoundary, OriginBoundary, RequestBodyBoundary
from starlette.responses import RedirectResponse


@pytest.fixture
def public_app(tmp_path):
    (tmp_path / "index.html").write_text("homepage")
    (tmp_path / "app.html").write_text("workspace")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__next._tree.txt").write_text("navigation payload")
    (tmp_path / "404.html").write_text("missing page")
    (tmp_path / "opengraph-image").write_bytes(b"0123456789")
    chunks = tmp_path / "_next/static/chunks"
    chunks.mkdir(parents=True)
    (chunks / "existing.js").write_text("export default 1;")
    api = FastAPI()

    @api.api_route("/api/echo", methods=["GET", "POST"])
    async def echo(request: Request):
        return {"headers": dict(request.headers), "body": (await request.body()).decode()}

    @api.get("/api/auth/google/callback")
    async def callback(request: Request):
        response = RedirectResponse("/app", status_code=302)
        response.set_cookie("session", request.query_params["code"], httponly=True)
        response.delete_cookie("oauth_state")
        return response

    api.add_middleware(RequestBodyBoundary)
    api.add_middleware(OriginBoundary)
    return CallbackLogBoundary(Frontend(
        api, origin=settings().origin, client_ip_header="x-rushes-ingress-client-ip", root=tmp_path,
    ))


async def test_static_navigation_errors_and_ranges(public_app):
    async with AsyncClient(transport=ASGITransport(public_app), base_url=settings().origin) as client:
        assert (await client.get("/app")).text == "workspace"
        assert (await client.get("/app/__next._tree.txt")).text == "navigation payload"
        assert (await client.get("/app/?q=one%20two")).headers["location"] == "/app?q=one%20two"
        for path in ("/missing", "/_next/static/chunks/missing.js"):
            for headers in ({}, {"Range": "bytes=0-9"}):
                response = await client.get(path, headers=headers)
                assert response.status_code == 404
                assert response.text == "missing page"
                assert response.headers["cache-control"] == "no-store"
                assert response.headers["x-frame-options"] == "DENY"
        response = await client.get("/_next/static/chunks/existing.js")
        assert "immutable" in response.headers["cache-control"]
        for value, code, content in (("bytes=0-0", 206, b"0"), ("bytes=-3", 206, b"789"), ("bytes=9-2", 400, None), ("bytes=99-100", 416, None)):
            response = await client.get("/opengraph-image", headers={"Range": value})
            assert response.status_code == code
            if content is not None:
                assert response.content == content
                assert response.headers["content-type"] == "image/png"
            else:
                assert response.headers["cache-control"] == "no-store"
        assert not (await client.head("/app")).content
        assert (await client.get("/app", headers={"Host": "attacker.example"})).status_code == 400


async def test_header_allowlist_origin_body_limit_and_cookies(public_app, monkeypatch):
    monkeypatch.setattr(settings(), "client_ip_header", "x-rushes-ingress-client-ip")
    async with AsyncClient(transport=ASGITransport(public_app), base_url=settings().origin) as client:
        response = await client.post("/api/echo", content=b"hello", headers={
            "Origin": settings().origin, "Cookie": "session=example", "Authorization": "drop-me",
            "X-Forwarded-For": "203.0.113.9", "X-Rushes-Client-IP": "203.0.113.9",
            "X-Rushes-Ingress-Client-IP": "192.0.2.4", "Last-Event-ID": "15",
        })
        assert response.status_code == 200
        echoed = response.json()
        assert echoed["body"] == "hello"
        assert echoed["headers"]["x-rushes-client-ip"] == "192.0.2.4"
        assert echoed["headers"]["last-event-id"] == "15"
        assert echoed["headers"]["cookie"] == "session=example"
        assert not ({"authorization", "x-forwarded-for", "x-rushes-ingress-client-ip"} & echoed["headers"].keys())
        assert (await client.post("/api/echo", content=b"x")).status_code == 403
        assert (await client.post("/api/echo", content=b"x", headers={"Origin": "https://attacker.example"})).status_code == 403
        assert (await client.post("/api/echo", content=b"x" * 65537, headers={"Origin": settings().origin})).status_code == 413
        options = await client.options("/api/echo")
        assert options.status_code == 204 and "POST" in options.headers["allow"]
        response = await client.get("/api/auth/google/callback?code=test-only", headers={"X-Rushes-Ingress-Client-IP": "192.0.2.4"})
        assert response.status_code == 302 and response.headers["location"] == "/app"
        assert len(response.headers.get_list("set-cookie")) == 2
        assert (await client.get("/api/auth/google/callback?code=test-only", headers={"X-Rushes-Client-IP": "192.0.2.4"})).status_code == 503


async def test_static_lookup_contains_symlinks_and_missing_error_page(tmp_path):
    outside = tmp_path / "private.txt"
    outside.write_text("private")
    root = tmp_path / "public"
    root.mkdir()
    (root / "leak.txt").symlink_to(outside)
    (root / "404.html").symlink_to(outside)
    app = Frontend(None, origin=settings().origin, root=root)
    async with AsyncClient(transport=ASGITransport(app), base_url=settings().origin) as client:
        for path in ("/leak.txt", "/missing", "/%2e%2e/private.txt"):
            response = await client.get(path)
            assert response.status_code == 404
            assert "private" not in response.text
