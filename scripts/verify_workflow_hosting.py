"""Verify the hosted supervisor and PostgreSQL workflow recovery in disposable resources."""

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
import psycopg
from psycopg import sql
from rushes.config import settings
from sqlalchemy.engine import make_url
from temporalio import workflow
from temporalio.client import Client
from temporalio.worker import UnsandboxedWorkflowRunner, Worker
from verify_hosting import ROOT, command, wait_for_health

PROBE_SCRIPT = "/qa/verify_workflow_hosting.py"


@workflow.defn
class RestartProbe:
    def __init__(self):
        self.released = False

    @workflow.run
    async def run(self) -> str:
        await workflow.wait_condition(lambda: self.released)
        return "resumed-from-postgres"

    @workflow.signal
    def release(self):
        self.released = True

    @workflow.query
    def waiting(self) -> bool:
        return not self.released


async def probe(mode: str):
    client = await Client.connect("127.0.0.1:7233")
    async with Worker(
        client,
        task_queue="rushes-host-restart-probe",
        workflows=[RestartProbe],
        workflow_runner=UnsandboxedWorkflowRunner(),
    ):
        if mode == "start":
            handle = await client.start_workflow(
                RestartProbe.run,
                id="rushes-host-restart-probe",
                task_queue="rushes-host-restart-probe",
            )
            assert await handle.query(RestartProbe.waiting)
            print("Durable probe waiting", flush=True)
        else:
            handle = client.get_workflow_handle("rushes-host-restart-probe")
            assert await handle.query(RestartProbe.waiting)
            await handle.signal(RestartProbe.release)
            assert await asyncio.wait_for(handle.result(), 30) == "resumed-from-postgres"
            print("Durable probe resumed", flush=True)


def service_processes():
    found = {}
    for path in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            args = path.read_bytes().rstrip(b"\0").split(b"\0")
        except (FileNotFoundError, ProcessLookupError):
            continue
        if args[0] == b"/opt/temporal/temporal-server":
            found["temporal"] = int(path.parent.name)
        elif args[1:] == [b"-m", b"rushes.worker"]:
            found["worker"] = int(path.parent.name)
    return found


def lifecycle_probe(mode: str):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        found = service_processes()
        if mode == "readiness" and "temporal" in found:
            assert "worker" not in found, "Worker started before private Temporal was ready"
            with socket.socket() as connection:
                assert connection.connect_ex(("127.0.0.1", 10000)) != 0
            return
        if mode in found and len(found) == 2:
            os.kill(found[mode], signal.SIGKILL)
            return
        time.sleep(0.1)
    raise TimeoutError("Expected RUSHES processes did not appear")


def verify_lifecycle(image, run, app, proxy, folder, client):
    start = [*run, "-d", "--name", app, "-p", "127.0.0.1:3844:10000", image]
    results = {}
    for case in ("readiness", "worker", "temporal"):
        command("docker", "rm", app)
        if case == "readiness":
            command("docker", "pause", proxy)
        try:
            command(*start)
            if case != "readiness":
                wait_for_health(client)
            command(
                "docker",
                "exec",
                app,
                "python",
                PROBE_SCRIPT,
                "lifecycle-" + case,
                timeout=20,
            )
            started = time.monotonic()
            if case == "readiness":
                command("docker", "stop", "--time", "20", app, timeout=25)
            code = command("docker", "wait", app, timeout=55)
            elapsed = round(time.monotonic() - started, 2)
            assert code == ("0" if case == "readiness" else "1"), (case, code)
            with socket.socket() as connection:
                assert connection.connect_ex(("127.0.0.1", 3844)) != 0
            results[case] = {"passed": True, "exit_code": int(code), "seconds": elapsed}
            logs = command("docker", "logs", app)
            (folder / f"{case}.log").write_text(logs)
        finally:
            if case == "readiness":
                command("docker", "unpause", proxy)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="rushes:production-amd64")
    parser.add_argument("--mount-source", action="store_true")
    args = parser.parse_args()
    image = args.image
    image_id = command("docker", "image", "inspect", image, "--format", "{{.Id}}")
    architecture = command("docker", "image", "inspect", image, "--format", "{{.Architecture}}")
    config = settings()
    admin = make_url(config.require_admin_database_url().get_secret_value())
    identity = uuid.uuid4().hex[:12]
    database = f"rushes_host_{identity}"
    databases = [database, database + "_wf", database + "_vis"]
    role = f"rushes_host_{identity}_workflow"
    app, volume = f"rushes-workflow-qa-{identity}", f"rushes-workflow-qa-{identity}"
    proxy = f"rushes-postgres-tls-qa-{identity}"
    folder = ROOT / ".local/workflow-hosting-qa" / identity
    folder.mkdir(parents=True, mode=0o700)
    certs = folder / "certs"
    certs.mkdir(mode=0o755)
    command(
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        str(certs / "server.key"),
        "-out",
        str(certs / "server.crt"),
        "-days",
        "1",
        "-subj",
        f"/CN={proxy}",
        "-addext",
        f"subjectAltName=DNS:{proxy}",
    )
    (certs / "server.key").chmod(0o444)
    origin = "http://localhost:3844"
    runtime = make_url(config.database_url.get_secret_value()).set(
        host="postgres", port=5432, database=database
    )
    workflow_url = admin.set(
        drivername="postgresql",
        host=proxy,
        port=5432,
        username=role,
        password=secrets.token_urlsafe(32),
        database=databases[1],
        query={"sslmode": "verify-full", "sslrootcert": "/certs/server.crt"},
    )
    env_file = folder / "runtime.env"
    env_file.write_text(
        "\n".join(
            [
                f"RUSHES_DATABASE_URL={runtime.render_as_string(hide_password=False)}",
                f"RUSHES_TEMPORAL_DATABASE_URL={workflow_url.render_as_string(hide_password=False)}",
                f"RUSHES_TEMPORAL_VISIBILITY_DATABASE_URL={workflow_url.set(database=databases[2]).render_as_string(hide_password=False)}",
                "RUSHES_HOST_WORKFLOW_SERVICE=true",
                "RUSHES_TEMPORAL_ADDRESS=127.0.0.1:7233",
                f"RUSHES_SECRET={secrets.token_hex(32)}",
                f"RUSHES_ORIGIN={origin}",
                "RUSHES_LOCAL_CREDITS=0",
                "RUSHES_GEMINI_API_KEY=",
                "RUSHES_COMPUTE_BACKEND=modal",
                "RUSHES_MEDIA_THREADS=1",
                "RUSHES_STORAGE_ROOT=/var/data/storage",
                "RUSHES_OUTPUT_ROOT=/var/data/exports",
            ]
        )
        + "\n"
    )
    env_file.chmod(0o600)
    mounts = [
        "-v",
        f"{ROOT / 'scripts'}:/qa:ro",
        "-v",
        f"{certs}:/certs:ro",
        "-v",
        f"{ROOT / 'tests/fixtures/held_ffmpeg.py'}:/usr/local/bin/ffmpeg:ro",
        "-v",
        f"{volume}:/var/data",
    ]
    if args.mount_source:
        mounts += [
            "-v",
            f"{ROOT / 'backend'}:/app/backend:ro",
            "-v",
            f"{ROOT / 'scripts'}:/app/scripts:ro",
            "-v",
            f"{ROOT / '.local/temporal-server'}:/opt/temporal:ro",
            "-e",
            "PYTHONPATH=/app/backend",
        ]
    run = [
        "docker",
        "run",
        "--network",
        "rushes_default",
        "--memory",
        "2g",
        "--memory-swap",
        "2g",
        "--cpus",
        "1",
        "--env-file",
        str(env_file),
        *mounts,
    ]
    created = []
    role_created = False
    with psycopg.connect(
        admin.set(drivername="postgresql").render_as_string(hide_password=False), autocommit=True
    ) as db:
        try:
            command(
                "docker",
                "run",
                "--rm",
                "-d",
                "--name",
                proxy,
                "--network",
                "rushes_default",
                "-v",
                f"{certs}:/certs:ro",
                "-v",
                f"{ROOT / 'tests/fixtures/postgres_tls_proxy.py'}:/fixture.py:ro",
                "--entrypoint",
                "python",
                image,
                "/fixture.py",
            )
            command(
                "docker",
                "exec",
                proxy,
                "python",
                "-c",
                "import socket,time; time.sleep(.5); socket.create_connection(('127.0.0.1',5432),timeout=3).close()",
            )
            db.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
                ).format(sql.Identifier(role), sql.Literal(workflow_url.password))
            )
            role_created = True
            for name in databases:
                owner = admin.username if name == database else role
                db.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {}").format(
                        sql.Identifier(name), sql.Identifier(owner)
                    )
                )
                created.append(name)
            command(
                str(ROOT / ".venv/bin/alembic"),
                "upgrade",
                "head",
                cwd=ROOT,
                env={
                    **os.environ,
                    "RUSHES_ADMIN_DATABASE_URL": admin.set(database=database).render_as_string(
                        hide_password=False
                    ),
                },
            )
            for _ in range(2):
                command(*run, "--rm", image, "python", "scripts/bootstrap_workflow_db.py")
            start = [*run, "-d", "--name", app, "-p", "127.0.0.1:3844:10000", image]
            command(*start)
            with httpx.Client(
                base_url=origin, timeout=20, trust_env=False, headers={"Origin": origin}
            ) as client:
                wait_for_health(client)
                email, password = f"workflow-{identity}@example.com", secrets.token_urlsafe(24)
                assert (
                    client.post(
                        "/api/auth/register",
                        json={
                            "email": email,
                            "password": password,
                            "name": "Synthetic workflow QA",
                        },
                    ).status_code
                    == 201
                )
                assert (
                    client.post(
                        "/api/auth/login", data={"username": email, "password": password}
                    ).status_code
                    == 204
                )
                ws = client.post(
                    "/api/workspaces", json={"name": "Synthetic hosted workflow"}
                ).json()["id"]
                base = f"/api/workspaces/{ws}"
                project = client.post(
                    base + "/projects", json={"name": "Synthetic hosted workflow"}
                ).json()["id"]
                fixture = folder / "SYNTHETIC-muted.mp4"
                command(
                    "ffmpeg",
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=blue:s=320x180:r=24",
                    "-t",
                    "2",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    str(fixture),
                )
                original = fixture.read_bytes()
                response = client.post(
                    f"{base}/projects/{project}/upload?filename={fixture.name}",
                    content=original,
                    headers={"Content-Type": "video/mp4"},
                )
                assert response.status_code == 202, response.text
                asset = response.json()["asset_id"]
                command(
                    "docker",
                    "exec",
                    app,
                    "python",
                    "-c",
                    "from pathlib import Path; import time; deadline=time.monotonic()+45\n"
                    "while not Path('/var/data/ffmpeg-held').exists() and time.monotonic()<deadline: time.sleep(.1)\n"
                    "assert Path('/var/data/ffmpeg-held').exists(), 'No active media unit was interrupted'",
                    timeout=50,
                )
                before = next(
                    job for job in client.get(base + "/jobs").json() if job["asset_id"] == asset
                )
                assert before["state"] == "running", before
                started = time.monotonic()
                command("docker", "stop", "--time", "55", app, timeout=60)
                active_shutdown = round(time.monotonic() - started, 2)
                assert command("docker", "inspect", app, "--format", "{{.State.ExitCode}}") == "0"
                command("docker", "rm", app)
                command(*start)
                wait_for_health(client)
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    state = client.get(f"{base}/assets/{asset}").json()
                    if state["status"] in {"partial", "ready", "failed"}:
                        break
                    time.sleep(0.5)
                assert state["status"] == "partial", state
                after = [
                    job for job in client.get(base + "/jobs").json() if job["asset_id"] == asset
                ]
                assert len(after) == 1 and after[0]["id"] == before["id"]
                assert after[0]["state"] == "partial", after
                media = f"{base}/assets/{asset}/media/proxy"
                preview = client.get(media, headers={"Range": "bytes=0-127"})
                assert preview.status_code == 206
                result = command(
                    "docker",
                    "exec",
                    app,
                    "python",
                    PROBE_SCRIPT,
                    "probe-start",
                )
                assert "Durable probe waiting" in result
                peak = int(command("docker", "exec", app, "cat", "/sys/fs/cgroup/memory.peak"))
                denied = subprocess.run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "--network",
                        "rushes_default",
                        "--entrypoint",
                        "python",
                        image,
                        "-c",
                        f"import socket; socket.create_connection(('{app}',7233),timeout=2)",
                    ],
                    capture_output=True,
                )
                assert denied.returncode != 0, "Temporal was reachable from another container"
                command("docker", "kill", app)
                command("docker", "rm", app)
                command(*start)
                wait_for_health(client)
                assert client.get("/api/auth/me").status_code == 200
                assert (
                    client.get(media, headers={"Range": "bytes=0-127"}).content == preview.content
                )
                result = command(
                    "docker",
                    "exec",
                    app,
                    "python",
                    PROBE_SCRIPT,
                    "probe-finish",
                )
                assert "Durable probe resumed" in result
                fingerprint = command(
                    "docker",
                    "exec",
                    app,
                    "python",
                    "-c",
                    "import hashlib,sys; from pathlib import Path; p=Path('/var/data/storage/uploads')/sys.argv[1]/sys.argv[2]/'original.mp4'; print(hashlib.sha256(p.read_bytes()).hexdigest())",
                    ws,
                    asset,
                )
                assert fingerprint == hashlib.sha256(original).hexdigest()
                started = time.monotonic()
                command("docker", "stop", "--time", "55", app)
                shutdown = round(time.monotonic() - started, 2)
                assert command("docker", "inspect", app, "--format", "{{.State.ExitCode}}") == "0"
                lifecycle = verify_lifecycle(image, run, app, proxy, folder, client)
                report = {
                    "checked_at": datetime.now(UTC).isoformat(),
                    "passed": True,
                    "image": image_id,
                    "architecture": architecture,
                    "production_source_mounted": args.mount_source,
                    "temporal_server": "1.31.2",
                    "schema_setup_idempotent": True,
                    "verified_tls_postgres_bootstrap_and_runtime": True,
                    "workflow_resumed_after_container_recreation": True,
                    "api_upload_processed_by_worker": True,
                    "active_media_resumed_after_shutdown": True,
                    "active_processing_shutdown_seconds": active_shutdown,
                    "same_job_after_restart": True,
                    "source_preserved": True,
                    "sessions_and_preview_preserved": True,
                    "temporal_unreachable_from_peer": True,
                    "peak_container_memory_bytes": peak,
                    "shutdown_seconds": shutdown,
                    "lifecycle": lifecycle,
                    "limits": "Local Docker, 2 GiB / 1 CPU. Synthetic two-second muted footage, no paid provider calls. Active media is held before FFmpeg executes, so this verifies job resumption but not interrupted partial-file cleanup. Not representative capacity or actual Render ingress verification.",
                }
                (ROOT / "docs/validation/workflow-hosting.json").write_text(
                    json.dumps(report, indent=2) + "\n"
                )
                print(
                    "PostgreSQL workflow recovery, real upload processing, isolation and shutdown passed",
                    flush=True,
                )
        except subprocess.CalledProcessError as error:
            (folder / "command-error.log").write_text((error.stdout or "") + (error.stderr or ""))
            raise
        finally:
            logs = subprocess.run(["docker", "logs", app], capture_output=True, text=True)
            (folder / "container.log").write_text(logs.stdout + logs.stderr)
            subprocess.run(["docker", "rm", "-f", app], capture_output=True)
            subprocess.run(["docker", "volume", "rm", volume], capture_output=True)
            subprocess.run(["docker", "rm", "-f", proxy], capture_output=True)
            for name in reversed(created):
                db.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
            if role_created:
                db.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
            env_file.unlink(missing_ok=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].startswith("probe-"):
        asyncio.run(probe(sys.argv[1].removeprefix("probe-")))
    elif len(sys.argv) > 1 and sys.argv[1].startswith("lifecycle-"):
        lifecycle_probe(sys.argv[1].removeprefix("lifecycle-"))
    else:
        main()
