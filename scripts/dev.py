"""Run the local RUSHES processes in the foreground; Ctrl-C stops only these children."""

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from rushes.config import settings


def occupied(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--production", action="store_true", help="Serve the exported web application without a Node server"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not (root / ".env").exists() or not (root / ".local/bin/temporal").exists():
        raise SystemExit(
            "Complete README setup first: private configuration, database migration, Temporal binary and web dependencies."
        )
    for port in (7233, 8233, 8741, 3741):
        if occupied(port):
            raise SystemExit(
                f"Port {port} is occupied. Stop the existing RUSHES service deliberately, or use its existing browser session."
            )
    if not occupied(55432):
        raise SystemExit(
            "Start PostgreSQL with docker compose up -d, then run scripts/bootstrap_db.py."
        )
    logs = root / ".local/logs"
    logs.mkdir(parents=True, exist_ok=True)
    children = []
    stopping = False

    def stop(_sig=None, _frame=None):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    def launch(name, command, cwd=root, env=None):
        with (logs / f"{name}.log").open("ab") as log:
            process = subprocess.Popen(
                command, cwd=cwd, stdout=log, stderr=log, start_new_session=True, env=env
            )
            children.append((name, process))
            return process

    try:
        server = launch(
            "temporal",
            [
                str(root / ".local/bin/temporal"),
                "server",
                "start-dev",
                "--ip",
                "127.0.0.1",
                "--db-filename",
                str(root / ".local/temporal.db"),
                "--ui-disable-news-fetch",
            ],
        )
        deadline = time.monotonic() + 60
        while not occupied(7233):
            if server.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("Temporal failed to start; inspect .local/logs/temporal.log")
            if stopping:
                return
            time.sleep(0.2)
        launch(
            "api",
            [
                sys.executable,
                "-m",
                "rushes.http_server",
                *([] if args.production else ["--api-only"]),
                "--host",
                "127.0.0.1",
                "--port",
                "3741" if args.production else "8741",
            ],
        )
        launch("worker", [sys.executable, "-m", "rushes.worker"])
        config = settings()
        web_env = {
            **os.environ,
            "PORT": "3741",
            "RUSHES_BIND_HOST": "127.0.0.1",
            **{"RUSHES_" + key.upper(): value for key, value in config.public_web_config.items()},
            "RUSHES_UPLOAD_TIMEOUT_SECONDS": str(config.upload_timeout_seconds),
        }
        if config.client_ip_header:
            web_env["RUSHES_CLIENT_IP_HEADER"] = config.client_ip_header
        if not args.production:
            launch("web", ["npm", "run", "dev"], root / "web", web_env)
        print("RUSHES: http://localhost:3741 · Temporal: http://localhost:8233", flush=True)
        print(
            "Logs: .local/logs · Ctrl-C stops this launcher’s children. Database and persisted work remain.",
            flush=True,
        )
        while not stopping:
            for name, process in children:
                if process.poll() is not None:
                    raise RuntimeError(f"{name} exited; inspect .local/logs/{name}.log")
            time.sleep(0.5)
    finally:
        # Stop workers before Temporal so completed units can checkpoint during graceful shutdown.
        for _name, process in reversed(children):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=35)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()


if __name__ == "__main__":
    main()
