"""Own an isolated PostgreSQL database, Temporal server, API and capped worker.

Requires the configured local PostgreSQL admin/runtime roles, Docker, the local
Temporal CLI, FFmpeg, and cached local model weights. Fixture generation uses macOS
say; pass --fixtures to use a previously generated manifest/corpus elsewhere.
No paid provider is enabled. SIGKILL targets only the labeled container we create.
"""

import argparse
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psycopg
from pipeline_fixtures import generate
from psycopg import sql
from rushes.config import settings
from sqlalchemy.engine import make_url


def main(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    repo = Path(__file__).resolve().parents[1]
    identity = secrets.token_hex(6)
    database = "rushes_pipeline_" + identity
    container = "rushes-pipeline-" + identity
    config = settings()
    admin = make_url(config.require_admin_database_url().get_secret_value())
    runtime = make_url(config.database_url.get_secret_value()).set(database=database)
    assert runtime.host in {"localhost", "127.0.0.1"}, "Only local PostgreSQL is supported"
    assert args.runs >= 2, "Repeated baseline and candidate runs are required"
    # Refuse occupied endpoints before starting anything or creating an account.
    for port in (args.api_port, args.temporal_port, args.temporal_port + 1000):
        with socket.socket() as probe:
            probe.bind(("0.0.0.0", port))
    processes = []

    def command(argv, **kwargs):
        return subprocess.run(argv, check=True, **kwargs)

    def launch(name, argv, env):
        with (root / (name + ".log")).open("ab") as log:
            process = subprocess.Popen(argv, env=env, stdout=log, stderr=log)
        processes.append(process)
        return process

    with psycopg.connect(
        admin.render_as_string(hide_password=False).replace("+psycopg", ""), autocommit=True
    ) as db:
        db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        try:
            values = {
                "RUSHES_DATABASE_URL": runtime.render_as_string(hide_password=False),
                "RUSHES_SECRET": secrets.token_urlsafe(40),
                "RUSHES_STORAGE_ROOT": str(root / "storage"),
                "RUSHES_OUTPUT_ROOT": str(root / "exports"),
                "RUSHES_SOURCE_ROOTS": "[]",
                "RUSHES_ORIGIN": f"http://127.0.0.1:{args.api_port}",
                "RUSHES_TEMPORAL_ADDRESS": f"127.0.0.1:{args.temporal_port}",
                "RUSHES_GEMINI_API_KEY": "",
                "RUSHES_PROVIDER_MONTHLY_ALLOWANCE_MICROUSD": "0",
                "RUSHES_COMPUTE_BACKEND": "local",
                "RUSHES_HOST_WORKFLOW_SERVICE": "false",
                "RUSHES_MEDIA_THREADS": "2",
                "RUSHES_MIN_FREE_BYTES": "0",
                "RUSHES_TRACE_FILE": str(root / "trace.jsonl"),
            }
            env = {
                **os.environ,
                **values,
                "RUSHES_ADMIN_DATABASE_URL": admin.set(database=database).render_as_string(
                    hide_password=False
                ),
            }
            command([str(Path(sys.executable).with_name("alembic")), "upgrade", "head"], env=env)
            (root / "exports").mkdir()
            shutil.copytree(config.storage_root / "models", root / "storage/models")
            fixtures = args.fixtures.resolve() if args.fixtures else root / "fixtures"
            if not args.fixtures:
                generate(fixtures)
            launch(
                "temporal",
                [
                    str(args.temporal),
                    "server",
                    "start-dev",
                    "--ip",
                    "127.0.0.1",
                    "--port",
                    str(args.temporal_port),
                    "--ui-port",
                    str(args.temporal_port + 1000),
                    "--db-filename",
                    str(root / "temporal.db"),
                ],
                env,
            )
            launch(
                "api",
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "rushes.api:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(args.api_port),
                ],
                env,
            )
            for _ in range(100):
                try:
                    if httpx.get(values["RUSHES_ORIGIN"] + "/api/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.2)
            else:
                raise RuntimeError("Isolated API did not become healthy")
            container_values = {
                **values,
                "PYTHONPATH": "/app/backend",
                "RUSHES_DATABASE_URL": runtime.set(host="host.docker.internal").render_as_string(
                    hide_password=False
                ),
                "RUSHES_TEMPORAL_ADDRESS": f"host.docker.internal:{args.temporal_port}",
            }
            env_file = root / "container.env"
            env_file.write_text("\n".join(k + "=" + v for k, v in container_values.items()) + "\n")
            env_file.chmod(0o600)
            for repeat in range(1, args.runs + 1):
                for label, concurrency in [("baseline", 1), ("candidate", 2)]:
                    tag = f"{label}-{repeat}"
                    command(
                        [
                            "docker",
                            "run",
                            "-d",
                            "--name",
                            container,
                            "--label",
                            "rushes.pipeline-study=true",
                            "--cpus",
                            "2",
                            "--memory",
                            "2g",
                            "--user",
                            "0",
                            "--env-file",
                            str(env_file),
                            "-e",
                            f"RUSHES_MEDIA_ACTIVITY_CONCURRENCY={concurrency}",
                            "-v",
                            f"{repo}/backend:/app/backend:ro",
                            "-v",
                            f"{repo}/scripts:/qa:ro",
                            "-v",
                            f"{root}:{root}",
                            args.image,
                            "python",
                            "-m",
                            "rushes.worker",
                        ]
                    )
                    command(
                        [
                            "docker",
                            "exec",
                            "-d",
                            container,
                            "python",
                            "/qa/sample_pipeline_memory.py",
                            str(root / (tag + "-memory.jsonl")),
                        ]
                    )
                    command(
                        [
                            sys.executable,
                            str(repo / "scripts/benchmark_pipeline.py"),
                            "--origin",
                            values["RUSHES_ORIGIN"],
                            "--fixtures",
                            str(fixtures),
                            "--output",
                            str(root / (tag + ".json")),
                            "--label",
                            tag,
                        ]
                    )
                    if repeat == args.runs and label == "candidate":
                        longest = max(
                            json.loads((fixtures / "manifest.json").read_text())["fixtures"],
                            key=lambda row: row["duration_seconds"],
                        )
                        command(
                            [
                                sys.executable,
                                str(repo / "scripts/verify_pipeline_recovery.py"),
                                "--origin",
                                values["RUSHES_ORIGIN"],
                                "--container",
                                container,
                                "--source",
                                str(fixtures / longest["file"]),
                                "--storage",
                                str(root / "storage"),
                                "--trace",
                                str(root / "trace.jsonl"),
                                "--output",
                                str(root / "recovery.json"),
                            ]
                        )
                    command(["docker", "stop", "-t", "40", container])
                    command(["docker", "rm", container])
        finally:
            subprocess.run(
                ["docker", "rm", "-f", container],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            for process in processes:
                process.terminate()
            for process in processes:
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            db.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
            (root / "container.env").unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", required=True, help="Pinned compatible RUSHES runtime image")
    parser.add_argument("--fixtures", type=Path)
    parser.add_argument("--temporal", type=Path, default=Path(".local/bin/temporal"))
    parser.add_argument("--api-port", type=int, default=8749)
    parser.add_argument("--temporal-port", type=int, default=7249)
    parser.add_argument("--runs", type=int, default=2)
    main(parser.parse_args())
