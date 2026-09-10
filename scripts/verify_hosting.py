"""Exercise the built image through real local TLS using disposable test resources."""

import argparse
import hashlib
import json
import os
import re
import secrets
import ssl
import subprocess
import time
import uuid
from pathlib import Path

import httpx
import psycopg
from psycopg import sql
from rushes.config import settings
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://localhost:3843"
IMAGE = "rushes:hosting-candidate"


def command(*args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs).stdout.strip()


def wait_for_health(client):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            if client.get("/api/health").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise RuntimeError("Container HTTPS health did not become ready")


def account(client):
    email, password = f"hosting-{uuid.uuid4()}@example.com", secrets.token_urlsafe(24)
    assert (
        client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "name": "Synthetic hosting QA"},
        ).status_code
        == 201
    )
    response = client.post("/api/auth/login", data={"username": email, "password": password})
    assert response.status_code == 204
    cookie = response.headers["set-cookie"].lower()
    assert "secure" in cookie and "httponly" in cookie and "samesite=strict" in cookie
    assert next(c for c in client.cookies.jar if c.name == "rushes_session").secure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slow-upload-seconds", type=int, default=345)
    args = parser.parse_args()
    if args.slow_upload_seconds < 0:
        parser.error("Upload duration must be nonnegative")
    config = settings()
    admin = make_url(config.require_admin_database_url().get_secret_value())
    identity = uuid.uuid4().hex[:12]
    database = f"rushes_hosting_qa_{identity}"
    app, ingress = f"rushes-hosting-qa-{identity}", f"rushes-tls-qa-{identity}"
    volume = f"rushes-hosting-qa-{identity}"
    folder = ROOT / ".local" / "hosting-qa" / identity
    folder.mkdir(parents=True, mode=0o700)
    image_id = command("docker", "image", "inspect", IMAGE, "--format", "{{.Id}}")
    image_arch = command("docker", "image", "inspect", IMAGE, "--format", "{{.Architecture}}")
    runtime = make_url(config.database_url.get_secret_value()).set(
        host="postgres", port=5432, database=database
    )
    env_file = folder / "runtime.env"
    with os.fdopen(os.open(env_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w") as file:
        file.write(
            "\n".join(
                [
                    f"RUSHES_DATABASE_URL={runtime.render_as_string(hide_password=False)}",
                    f"RUSHES_SECRET={secrets.token_hex(32)}",
                    f"RUSHES_ORIGIN={ORIGIN}",
                    "RUSHES_CLIENT_IP_HEADER=x-rushes-ingress-client-ip",
                    "RUSHES_LOCAL_CREDITS=0",
                ]
            )
            + "\n"
        )
    caddy = folder / "Caddyfile"
    caddy.write_text(
        "{\n admin off\n auto_https disable_redirects\n}\nhttps://localhost {\n tls internal\n reverse_proxy "
        + app
        + ":10000 {\n  header_up X-Rushes-Ingress-Client-IP {remote_host}\n }\n}\n"
    )
    fixture = folder / "SYNTHETIC-container.mp4"
    command(
        "ffmpeg",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=160x90:rate=24",
        "-t",
        "2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(fixture),
    )
    original = fixture.read_bytes()
    db_created = False
    with psycopg.connect(
        admin.render_as_string(hide_password=False).replace("+psycopg", ""), autocommit=True
    ) as db:
        try:
            db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
            db_created = True
            migration_env = {
                **os.environ,
                "RUSHES_ADMIN_DATABASE_URL": admin.set(database=database).render_as_string(
                    hide_password=False
                ),
            }
            command(str(ROOT / ".venv/bin/alembic"), "upgrade", "head", env=migration_env, cwd=ROOT)
            command(
                "docker",
                "run",
                "-d",
                "--name",
                app,
                "--platform",
                f"linux/{image_arch}",
                "--network",
                "rushes_default",
                "--memory",
                "1g",
                "--memory-swap",
                "1g",
                "--cpus",
                "1",
                "--env-file",
                str(env_file),
                "-v",
                f"{volume}:/var/data",
                IMAGE,
            )
            command(
                "docker",
                "run",
                "-d",
                "--name",
                ingress,
                "--network",
                "rushes_default",
                "-p",
                "127.0.0.1:3843:443",
                "--tmpfs",
                "/data",
                "--tmpfs",
                "/config",
                "-v",
                f"{caddy}:/etc/caddy/Caddyfile:ro",
                "caddy:2-alpine",
            )
            ca = folder / "root.crt"
            for _ in range(60):
                result = subprocess.run(
                    [
                        "docker",
                        "exec",
                        ingress,
                        "cat",
                        "/data/caddy/pki/authorities/local/root.crt",
                    ],
                    capture_output=True,
                )
                if result.returncode == 0:
                    ca.write_bytes(result.stdout)
                    break
                time.sleep(0.5)
            assert ca.is_file(), "Local TLS authority was not created"
            tls = ssl.create_default_context(cafile=str(ca))
            with (
                httpx.Client(
                    base_url=ORIGIN,
                    verify=tls,
                    trust_env=False,
                    timeout=40,
                    headers={"Origin": ORIGIN},
                ) as owner,
                httpx.Client(
                    base_url=ORIGIN,
                    verify=tls,
                    trust_env=False,
                    timeout=40,
                    headers={"Origin": ORIGIN},
                ) as outsider,
            ):
                wait_for_health(owner)
                print("HTTPS is ready; checking assets, sessions and upload.", flush=True)
                page = owner.get("/")
                assert page.status_code == 200
                assets = set(re.findall(r'(?:src|href)="(/_next/static/[^"?]+)', page.text))
                assert any(path.endswith(".css") for path in assets)
                assert any(path.endswith(".js") for path in assets)
                for path in assets:
                    assert owner.get(path).status_code == 200, path
                account(owner)
                account(outsider)
                assert (
                    command(
                        "docker",
                        "exec",
                        app,
                        "python",
                        "-c",
                        "import http.client; c=http.client.HTTPConnection('127.0.0.1',10000); c.request('GET','/api/health',headers={'Host':'evil.example'}); print(c.getresponse().status)",
                    )
                    == "400"
                )
                assert (
                    owner.get("/api/health", headers={"Origin": "https://evil.example"}).status_code
                    == 403
                )
                missing_origin = owner.build_request(
                    "POST", "/api/workspaces", json={"name": "Rejected"}
                )
                del missing_origin.headers["Origin"]
                assert owner.send(missing_origin).status_code == 403
                workspace = owner.post(
                    "/api/workspaces", json={"name": "Synthetic container verification"}
                ).json()["id"]
                base = f"/api/workspaces/{workspace}"
                project = owner.post(
                    base + "/projects", json={"name": "Synthetic TLS upload"}
                ).json()["id"]

                def upload_chunks():
                    parts = max(1, args.slow_upload_seconds)
                    for index in range(parts):
                        if args.slow_upload_seconds:
                            time.sleep(args.slow_upload_seconds / parts)
                        yield original[
                            len(original) * index // parts : len(original) * (index + 1) // parts
                        ]

                started = time.monotonic()
                response = owner.post(
                    f"{base}/projects/{project}/upload?filename={fixture.name}",
                    content=upload_chunks(),
                    headers={"Content-Type": "video/mp4"},
                )
                assert response.status_code == 202
                upload_seconds = round(time.monotonic() - started, 2)
                print(
                    f"Upload accepted after {upload_seconds}s; checking preview and restart.",
                    flush=True,
                )
                asset = response.json()["asset_id"]
                assert outsider.get(f"{base}/assets/{asset}").status_code == 404
                command(
                    "docker",
                    "exec",
                    app,
                    "python",
                    "-c",
                    "import asyncio,sys; from rushes.pipeline import prepare_asset; asyncio.run(prepare_asset(sys.argv[1],sys.argv[2]))",
                    workspace,
                    asset,
                )
                media_url = f"{base}/assets/{asset}/media/proxy"
                preview = owner.get(media_url, headers={"Range": "bytes=0-127"})
                assert preview.status_code == 206 and len(preview.content) == 128
                fingerprint = command(
                    "docker",
                    "exec",
                    app,
                    "python",
                    "-c",
                    "import hashlib,sys; from pathlib import Path; from rushes.config import settings; p=settings().storage_root/'uploads'/sys.argv[1]/sys.argv[2]/'original.mp4'; print(hashlib.sha256(p.read_bytes()).hexdigest()); assert settings().admin_database_url is None",
                    workspace,
                    asset,
                )
                assert fingerprint == hashlib.sha256(original).hexdigest()
                denied = subprocess.run(
                    [
                        "docker",
                        "exec",
                        ingress,
                        "wget",
                        "-T",
                        "2",
                        "-qO-",
                        f"http://{app}:8741/api/health",
                    ],
                    capture_output=True,
                )
                assert denied.returncode != 0, "Private API was reachable from another container"
                assert command("docker", "exec", app, "id", "-u") == "10001"
                with owner.stream("GET", f"{base}/events?project_id={project}") as stream:
                    assert next(stream.iter_lines()).startswith("data:")
                    started = time.monotonic()
                    command("docker", "stop", "--time", "25", app)
                    shutdown_seconds = round(time.monotonic() - started, 2)
                assert command("docker", "inspect", app, "--format", "{{.State.ExitCode}}") == "0"
                assert shutdown_seconds < 23
                command("docker", "start", app)
                wait_for_health(owner)
                assert owner.get("/api/auth/me").status_code == 200
                assert (
                    owner.get(media_url, headers={"Range": "bytes=0-127"}).content
                    == preview.content
                )
                # The ingress overwrites forged identity headers; they cannot replenish the auth budget.
                for index in range(10):
                    assert (
                        owner.post(
                            "/api/auth/login",
                            json={},
                            headers={
                                "x-rushes-ingress-client-ip": f"192.0.2.{index + 1}",
                                "x-rushes-client-ip": f"198.51.100.{index + 1}",
                            },
                        ).status_code
                        == 422
                    )
                assert (
                    owner.post(
                        "/api/auth/login",
                        json={},
                        headers={"x-rushes-ingress-client-ip": "203.0.113.1"},
                    ).status_code
                    == 429
                )
                report = {
                    "passed": True,
                    "image_id": image_id,
                    "architecture": f"linux/{image_arch}",
                    "tls": "Local CA verified without modifying system trust",
                    "secure_sessions": True,
                    "runtime_admin_credentials": False,
                    "source_preserved": True,
                    "upload_and_preview_after_restart": True,
                    "static_assets_served": len(assets),
                    "upload_seconds": upload_seconds,
                    "upload_exceeded_default_node_deadline": upload_seconds > 335,
                    "cross_workspace_denied": True,
                    "private_api_unreachable_from_ingress": True,
                    "spoofed_client_identity_did_not_bypass_limit": True,
                    "shutdown_with_sse_seconds": shutdown_seconds,
                    "limits": "Disposable local image verification at 1 GiB/1 CPU; preview prepared with the actual module directly. Not hosted production, Modal/Temporal worker integration, or a capacity benchmark.",
                }
                (ROOT / "docs/validation/hosting-container.json").write_text(
                    json.dumps(report, indent=2) + "\n"
                )
                print(
                    "Container HTTPS, secure sessions, upload/preview persistence, isolation and shutdown checks passed."
                )
        finally:
            for name in (ingress, app):
                logs = subprocess.run(["docker", "logs", name], capture_output=True, text=True)
                (folder / f"{name}.log").write_text(logs.stdout + logs.stderr)
                subprocess.run(["docker", "rm", "-f", name], capture_output=True)
            subprocess.run(["docker", "volume", "rm", volume], capture_output=True)
            if db_created:
                db.execute(
                    sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database))
                )
            env_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
