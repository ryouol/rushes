"""Run the public web server and its private API in one service container."""

import asyncio
import os
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import suppress
from pathlib import Path

from rushes.config import settings
from rushes.workflow_service import wait_for_namespace, write_server_config


def main():
    if not os.environ.get("RUSHES_ORIGIN") and os.environ.get("RENDER_EXTERNAL_URL"):
        os.environ["RUSHES_ORIGIN"] = os.environ["RENDER_EXTERNAL_URL"]
    if not os.environ.get("RUSHES_ORIGIN"):
        raise SystemExit("Set RUSHES_ORIGIN to the public HTTPS origin before starting the service")
    config = settings()
    if config.origin.startswith("https:") and not config.client_ip_header:
        raise SystemExit(
            "Set RUSHES_CLIENT_IP_HEADER to a header overwritten by the trusted ingress"
        )
    for path in (config.storage_root, config.output_root):
        path.mkdir(parents=True, exist_ok=True)
    port = int(os.environ.get("PORT", "10000"))
    if not 1 <= port <= 65535 or port == 8741:
        raise SystemExit(
            "PORT must be between 1 and 65535 and cannot use the private API port 8741"
        )
    root = Path(__file__).resolve().parents[1]
    stopping = False
    children = []
    temporal = None

    def stop(_signal, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with tempfile.TemporaryDirectory(prefix="rushes-workflow-") as temporary:
        try:
            if config.host_workflow_service:
                path = Path(temporary) / "temporal.yaml"
                write_server_config(config, path)
                temporal = subprocess.Popen(
                    [
                        "/opt/temporal/temporal-server",
                        "--config-file",
                        str(path),
                        "--allow-no-auth",
                        "start",
                    ],
                    env={**os.environ, "GOMEMLIMIT": "512MiB", "GOMAXPROCS": "1"},
                    start_new_session=True,
                )
                if (
                    not asyncio.run(
                        wait_for_namespace(config.temporal_address, stopping=lambda: stopping)
                    )
                    or stopping
                ):
                    return
                children.append(
                    subprocess.Popen(
                        [sys.executable, "-m", "rushes.worker"],
                        start_new_session=True,
                    )
                )
            if stopping:
                return
            children.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "rushes.api:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "8741",
                        "--no-proxy-headers",
                        "--timeout-graceful-shutdown",
                        "10",
                    ],
                    start_new_session=True,
                )
            )
            children.append(
                subprocess.Popen(
                    ["node", "server.mjs"],
                    cwd=root / "web",
                    env={
                        **os.environ,
                        "RUSHES_BIND_HOST": "0.0.0.0",
                        "PORT": str(port),
                        "RUSHES_UPLOAD_TIMEOUT_SECONDS": str(config.upload_timeout_seconds),
                    },
                    start_new_session=True,
                )
            )
            while not stopping:
                if any(child.poll() is not None for child in children) or (
                    temporal is not None and temporal.poll() is not None
                ):
                    raise SystemExit("A RUSHES service exited; stopping its companion")
                time.sleep(0.5)
        finally:
            for child in reversed(children):
                if child.poll() is None:
                    with suppress(ProcessLookupError):
                        os.killpg(child.pid, signal.SIGTERM)
            deadline = time.monotonic() + (35 if temporal is not None else 20)
            for child in reversed(children):
                try:
                    child.wait(timeout=max(0, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    with suppress(ProcessLookupError):
                        os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
            if temporal is not None and temporal.poll() is None:
                with suppress(ProcessLookupError):
                    os.killpg(temporal.pid, signal.SIGTERM)
                try:
                    temporal.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    with suppress(ProcessLookupError):
                        os.killpg(temporal.pid, signal.SIGKILL)
                    temporal.wait()


if __name__ == "__main__":
    main()
