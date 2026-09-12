"""Interrupt only explicitly selected RUSHES services, then verify durable recovery on synthetic media."""

import argparse
import hashlib
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
from rushes.config import settings


def port_ready(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def stop_existing(pid, expected):
    command = subprocess.check_output(["ps", "-p", str(pid), "-o", "command="], text=True)
    if expected not in command:
        raise SystemExit(
            "Refusing to stop a process that does not match the selected RUSHES service"
        )
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    raise RuntimeError("Selected service did not stop")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker-pid", type=int, required=True)
    parser.add_argument("--temporal-pid", type=int, required=True)
    args = parser.parse_args()
    config = settings()
    if config.gemini_api_key and config.gemini_api_key.get_secret_value():
        raise SystemExit(
            "Use a separate provider-disabled test instance for synthetic recovery verification"
        )
    folder = Path(".local/recovery")
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / "SYNTHETIC-restart-1080p.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=purple:size=1920x1080:rate=24:duration=300",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-threads",
            "2",
            str(source),
        ],
        check=True,
    )
    original = hashlib.sha256(source.read_bytes()).hexdigest()

    def launch(name, command):
        with (folder / f"{name}.log").open("ab") as log:
            return subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)

    def worker():
        return launch("worker", [sys.executable, "-m", "rushes.worker"])

    identity = secrets.token_hex(6)
    with httpx.Client(
        base_url=config.origin + "/api", headers={"Origin": config.origin}, timeout=90
    ) as client:
        email, password = f"recovery-{identity}@example.com", secrets.token_urlsafe(30)
        client.post(
            "/auth/register",
            json={"name": "Synthetic recovery QA", "email": email, "password": password},
        ).raise_for_status()
        client.post(
            "/auth/login", data={"username": email, "password": password}
        ).raise_for_status()
        workspace = client.post(
            "/workspaces", json={"name": "SYNTHETIC interruption verification"}
        ).json()["id"]
        base = f"/workspaces/{workspace}"
        project = client.post(
            f"{base}/projects", json={"name": "SYNTHETIC worker and server restart"}
        ).json()["id"]
        stop_existing(args.worker_pid, "-m rushes.worker")
        response = client.post(
            f"{base}/projects/{project}/upload",
            params={"filename": source.name},
            content=source.read_bytes(),
        )
        response.raise_for_status()
        asset = response.json()["asset_id"]
        broken = client.post(
            f"{base}/projects/{project}/upload",
            params={"filename": "SYNTHETIC-corrupt.mp4"},
            content=b"Intentionally invalid media for per-file failure verification",
        )
        broken.raise_for_status()
        running = worker()
        start = time.monotonic()
        interrupted = False
        deadline = start + 90
        while time.monotonic() < deadline:
            state = client.get(f"{base}/assets/{asset}").json()["status"]
            units = list((config.storage_root / workspace / asset).rglob("*.partial*"))
            if state == "processing" and units:
                os.killpg(running.pid, signal.SIGKILL)
                running.wait()
                interrupted = True
                break
            if running.poll() is not None:
                raise RuntimeError("Worker exited; inspect .local/recovery/worker.log")
            time.sleep(0.05)
        if not interrupted:
            raise RuntimeError(
                "No active media unit was interrupted; do not claim restart verification"
            )
        stop_existing(args.temporal_pid, "temporal server start-dev")
        temporal = launch(
            "temporal",
            [
                str(Path(".local/bin/temporal").resolve()),
                "server",
                "start-dev",
                "--ip",
                "127.0.0.1",
                "--db-filename",
                str(Path(".local/temporal.db").resolve()),
                "--ui-disable-news-fetch",
            ],
        )
        deadline = time.monotonic() + 60
        while not port_ready(7233):
            if time.monotonic() > deadline or temporal.poll() is not None:
                raise RuntimeError("Temporal restart failed; inspect .local/recovery/temporal.log")
            time.sleep(0.2)
        running = worker()
        (folder / "services.json").write_text(
            json.dumps({"worker_pid": running.pid, "temporal_pid": temporal.pid})
        )
        deadline = time.monotonic() + 300
        last = None
        while time.monotonic() < deadline:
            jobs = client.get(f"{base}/jobs", params={"project_id": project}).json()
            states = [job["state"] for job in jobs]
            if states != last:
                print(f"Recovery states: {states}", flush=True)
                last = states
            if len(jobs) == 2 and all(state in {"partial", "failed"} for state in states):
                break
            time.sleep(2)
        good = client.get(f"{base}/assets/{asset}").json()
        usage = client.get(f"{base}/usage").json()
        observation_before = client.get(f"{base}/assets/{asset}/observations").json()
        report = {
            "fixture": "SYNTHETIC 300-second 1080p24 muted purple source plus intentionally corrupt file",
            "interrupted_in_flight": interrupted,
            "interruption": "SIGKILL of owned worker process group during an active temporary media unit; Temporal server stopped and reopened the same SQLite state",
            "elapsed_seconds": round(time.monotonic() - start, 2),
            "job_states": states,
            "asset_status": good["status"],
            "has_preview": good["has_preview"],
            "usage": usage,
            "original_unchanged": hashlib.sha256(source.read_bytes()).hexdigest() == original,
            "workspace_id": workspace,
            "project_id": project,
            "asset_id": asset,
            "source_usage_records": next(
                (row["attempts"] for row in usage["metrics"] if row["kind"] == "source"), 0
            ),
            "observation_count": observation_before["total"],
        }
        report["passed"] = (
            good["status"] == "partial"
            and good["has_preview"]
            and sorted(states) == ["failed", "partial"]
            and report["source_usage_records"] == 1
            and report["original_unchanged"]
            and len(usage["ledger"]) == 1
        )
        (folder / "results.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2), flush=True)
        if not report["passed"]:
            raise SystemExit("Recovery verification failed")


if __name__ == "__main__":
    main()
