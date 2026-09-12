"""Measure a 10-hour / 50-file synthetic ingestion load; never a semantic quality benchmark."""

import hashlib
import json
import platform
import secrets
import subprocess
import time
from pathlib import Path

import httpx
from rushes.config import settings


def source_digest(path):
    with Path(path).open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def main():
    folder = Path(".local/benchmark")
    folder.mkdir(parents=True, exist_ok=True)
    master = folder / "SYNTHETIC-master.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:size=160x90:rate=24:duration=360",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:size=160x90:rate=24:duration=360",
            "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0[v]",
            "-map",
            "[v]",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "35",
            str(master),
        ],
        check=True,
    )
    identity = secrets.token_hex(6)
    origins = {"Origin": settings().origin}
    report = {
        "fixture": "SYNTHETIC repeated red/blue patterns; no audio; not representative footage",
        "files": 50,
        "source_hours": 10,
        "resolution": "160x90",
        "frame_rate": "24/1",
        "hardware": platform.platform(),
        "architecture": platform.machine(),
        "memory_bytes": 17179869184,
        "provider_requests_expected": 0,
        "semantic_evaluation": "not performed; requires representative footage and human labels",
    }
    if settings().gemini_api_key and settings().gemini_api_key.get_secret_value():
        raise SystemExit(
            "Synthetic load run requires Gemini disabled to avoid unnecessary provider charges"
        )
    with httpx.Client(base_url=settings().origin + "/api", headers=origins, timeout=180) as client:
        email, password = f"synthetic-load-{identity}@example.com", secrets.token_urlsafe(32)
        client.post(
            "/auth/register",
            json={"name": "Synthetic load verification", "email": email, "password": password},
        ).raise_for_status()
        client.post(
            "/auth/login", data={"username": email, "password": password}
        ).raise_for_status()
        response = client.post("/workspaces", json={"name": f"SYNTHETIC 10-hour load {identity}"})
        response.raise_for_status()
        workspace = response.json()["id"]
        response = client.post(
            f"/workspaces/{workspace}/projects",
            json={
                "name": "SYNTHETIC 50-file durability run",
                "description": "Generated red/blue timing load. No real footage or semantic quality claim.",
            },
        )
        response.raise_for_status()
        project = response.json()["id"]
        report.update(workspace_id=workspace, project_id=project)
        (folder / "run.json").write_text(json.dumps(report, indent=2))
        started = time.monotonic()
        sources = {}
        for index in range(50):
            source = folder / f"SYNTHETIC-{index + 1:02d}.mp4"
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    str(master),
                    "-c",
                    "copy",
                    "-metadata",
                    f"title=Synthetic timing load source {index + 1}",
                    str(source),
                ],
                check=True,
            )
            sources[str(source)] = source_digest(source)
            with source.open("rb") as file:
                response = client.post(
                    f"/workspaces/{workspace}/projects/{project}/upload",
                    params={"filename": source.name},
                    content=file,
                    headers={
                        "Content-Type": "application/octet-stream",
                        "Content-Length": str(source.stat().st_size),
                    },
                )
            response.raise_for_status()
            if (index + 1) % 10 == 0:
                print(f"Queued {index + 1}/50 synthetic files", flush=True)
        previous = None
        while time.monotonic() - started < 3600:
            response = client.get(f"/workspaces/{workspace}/jobs", params={"project_id": project})
            response.raise_for_status()
            jobs = response.json()
            states = {}
            for job in jobs:
                states[job["state"]] = states.get(job["state"], 0) + 1
            if states != previous:
                print(
                    json.dumps(
                        {"elapsed_seconds": round(time.monotonic() - started, 1), "states": states}
                    ),
                    flush=True,
                )
                previous = states
            if len(jobs) == 50 and not any(
                job["state"] in {"queued", "dispatched", "running"} for job in jobs
            ):
                break
            time.sleep(5)
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        report["job_states"] = states
        report["jobs"] = [
            {"id": job["id"], "state": job["state"], "error": job["error"]} for job in jobs
        ]
        report["usage"] = client.get(f"/workspaces/{workspace}/usage").json()
        report["originals_preserved"] = all(
            source_digest(path) == digest for path, digest in sources.items()
        )
        report["complete"] = len(jobs) == 50 and all(job["state"] == "partial" for job in jobs)
        report["partial_reason"] = "Gemini deliberately not configured; no speech in fixture"
        (folder / "results.json").write_text(json.dumps(report, indent=2))
        print(f"Synthetic load report written to {folder / 'results.json'}", flush=True)


if __name__ == "__main__":
    main()
