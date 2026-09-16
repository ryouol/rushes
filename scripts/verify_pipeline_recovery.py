"""SIGKILL only the labeled disposable benchmark container after a transcript checkpoint.

Requires an isolated provider-disabled instance and its private trace/storage paths.
Leaves evidence in --output; does not touch the Temporal server or production worker.
"""

import argparse
import hashlib
import json
import secrets
import subprocess
import time
from pathlib import Path

import httpx


def trace_rows(path):
    rows = []
    for line in path.read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass  # A concurrent writer may not have completed the final line.
    return rows


def hashes(folder):
    return {
        str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in folder.rglob("*")
        if p.is_file() and (p.name == "manifest.json" or p.name.startswith("transcript-"))
    }


def run(args):
    info = json.loads(subprocess.check_output(["docker", "inspect", args.container]))[0]
    assert info["Config"]["Labels"].get("rushes.pipeline-study") == "true", (
        "Requires disposable benchmark label"
    )
    env = dict(pair.split("=", 1) for pair in info["Config"]["Env"])
    assert not env.get("RUSHES_GEMINI_API_KEY") and env["RUSHES_COMPUTE_BACKEND"] == "local"
    identity = secrets.token_hex(8)
    with httpx.Client(
        base_url=args.origin + "/api", headers={"Origin": args.origin}, timeout=300
    ) as client:

        def post(path, **kwargs):
            r = client.post(path, **kwargs)
            r.raise_for_status()
            return r.json() if r.content else None

        email, password = f"recovery-{identity}@example.com", secrets.token_urlsafe(32)
        post(
            "/auth/register",
            json={"name": "Isolated crash test", "email": email, "password": password},
        )
        post("/auth/login", data={"username": email, "password": password})
        ws = post("/workspaces", json={"name": "SYNTHETIC checkpoint recovery"})["id"]
        base = f"/workspaces/{ws}"
        project = post(base + "/projects", json={"name": "Checkpoint recovery"})["id"]
        with args.source.open("rb") as file:
            asset = post(
                base + f"/projects/{project}/upload",
                params={"filename": args.source.name},
                content=file,
                headers={"Content-Length": str(args.source.stat().st_size)},
            )["asset_id"]
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            starts = [
                r
                for r in trace_rows(args.trace)
                if r.get("asset_id") == asset
                and r["name"] == "provider.transcription"
                and r["event"] == "start"
            ]
            if len(starts) == 2:
                break
            assert len(starts) < 2, "Missed the selected checkpoint"
            time.sleep(0.025)
        assert len(starts) == 2
        folder = args.storage / ws / asset
        before = hashes(folder)
        assert sum("transcript-" in p for p in before) == 1, before
        killed_ns = time.time_ns()
        subprocess.run(["docker", "kill", "--signal", "KILL", args.container], check=True)
        subprocess.run(["docker", "start", args.container], check=True)
        restarted_ns = time.time_ns()
        while time.monotonic() < deadline:
            jobs = client.get(base + "/jobs", params={"project_id": project}).json()
            job = next(j for j in jobs if j["asset_id"] == asset)
            if job["state"] in {"ready", "partial", "failed"}:
                break
            time.sleep(0.1)
        assert job["state"] in {"ready", "partial"}, job
        finished_ns = time.time_ns()
        rows = [r for r in trace_rows(args.trace) if r.get("asset_id") == asset]
        retries = [
            r
            for r in rows
            if r["name"] == "activity.transcribe" and r["event"] == "start" and r["attempt"] > 1
        ]
        assert len(retries) == 1
        calls = [r for r in rows if r["name"] == "provider.transcription" and r["event"] == "start"]
        completed = [
            r
            for r in rows
            if r["name"] == "provider.transcription" and r["event"] == "end" and r["status"] == "ok"
        ]
        after = hashes(folder)
        assert all(after.get(p) == checksum for p, checksum in before.items())
        assert sum(r["start_us"] == 0 for r in calls) == 1
        assert sum(r["start_us"] == 60000000 for r in calls) == 2
        assert len(completed) == 3
        report = {
            "asset_id": asset,
            "job_id": job["id"],
            "workspace_id": ws,
            "checkpoint": "first 60-second transcript persisted; second transcription invocation started",
            "killed_ns": killed_ns,
            "restarted_ns": restarted_ns,
            "finished_ns": finished_ns,
            "recovery_to_retry_seconds": (retries[0]["time_ns"] - killed_ns) / 1e9,
            "recovery_to_searchable_seconds": (finished_ns - killed_ns) / 1e9,
            "checkpoint_hashes_unchanged": True,
            "completed_media_minutes_recomputed": 0,
            "inflight_media_minutes_reissued": 1,
            "transcription_invocations": len(calls),
            "successful_transcription_invocations": len(completed),
            "duplicate_completed_transcription_windows": 0,
            "paid_provider_requests": 0,
            "provider_scope": "real local faster-whisper; Gemini deliberately disabled",
            "activity_attempts": [
                r["attempt"]
                for r in rows
                if r["name"] == "activity.transcribe" and r["event"] == "start"
            ],
            "observations": client.get(base + f"/assets/{asset}/observations").json(),
        }
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({k: v for k, v in report.items() if k != "observations"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--container", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--storage", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
