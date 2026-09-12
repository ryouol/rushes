import os
import signal
import socket
import subprocess
import sys
import time

import httpx


def test_fatal_worker_error_stops_real_uvicorn_after_lifespan_cleanup(tmp_path):
    trigger, cleaned = tmp_path / "trigger", tmp_path / "cleaned"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    script = """
import asyncio, sys
from contextlib import asynccontextmanager
from pathlib import Path
import uvicorn
from rushes import worker

@asynccontextmanager
async def running():
    fatal = asyncio.get_running_loop().create_future()
    async def trigger():
        while not Path(sys.argv[2]).exists():
            await asyncio.sleep(.02)
        fatal.set_exception(RuntimeError("Synthetic fatal worker error"))
        await asyncio.Future()
    task = asyncio.create_task(trigger())
    try:
        yield [task, fatal]
    finally:
        task.cancel()
        await asyncio.gather(task, fatal, return_exceptions=True)
        Path(sys.argv[3]).write_text("drained")
worker.running_workers = running
from rushes.api import app
uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
"""
    with (tmp_path / "server.log").open("w+") as log:
        process = subprocess.Popen(
            [sys.executable, "-c", script, str(port), str(trigger), str(cleaned)],
            env={**os.environ, "RUSHES_HOST_WORKFLOW_SERVICE": "true"},
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 10
            with httpx.Client(
                base_url=f"http://127.0.0.1:{port}", timeout=1, trust_env=False
            ) as client:
                while True:
                    assert process.poll() is None, "Server exited before readiness"
                    try:
                        if client.get("/api/health").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    assert time.monotonic() < deadline, "Server did not become ready"
                    time.sleep(0.05)
            trigger.touch()
            assert process.wait(timeout=5) in (0, -signal.SIGTERM)
            assert cleaned.read_text() == "drained"
            with socket.socket() as listener:
                assert listener.connect_ex(("127.0.0.1", port)) != 0
            log.seek(0)
            assert "Synthetic fatal worker error" in log.read()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
