"""Exercise a separately launched, provider-disabled instance; never interrupts services.

Requires --origin and --output. The caller owns isolation and worker resource limits.
Cold means new assets/checkpoints, with downloaded model weights already available.
"""

import argparse
import hashlib
import json
import math
import secrets
import time
from pathlib import Path

import httpx
from pipeline_fixtures import QUERIES


def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


def run(origin, fixtures, output, label):
    manifest = json.loads((fixtures / "manifest.json").read_text())
    report = {"label": label, "fixtures": manifest, "runs": [], "queries": []}

    def save():
        output.write_text(json.dumps(report, indent=2) + "\n")

    with httpx.Client(
        base_url=origin + "/api",
        headers={
            "Origin": origin,
            "traceparent": "00-" + secrets.token_hex(16) + "-" + secrets.token_hex(8) + "-01",
        },
        timeout=300,
    ) as client:

        def post(path, **kwargs):
            response = client.post(path, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else None

        identity = secrets.token_hex(6)
        email, password = f"pipeline-{identity}@example.com", secrets.token_urlsafe(32)
        post(
            "/auth/register",
            json={"name": "Synthetic pipeline study", "email": email, "password": password},
        )
        post("/auth/login", data={"username": email, "password": password})
        ws = post("/workspaces", json={"name": f"SYNTHETIC pipeline {label}"})["id"]
        base = f"/workspaces/{ws}"
        project = post(base + "/projects", json={"name": label})["id"]
        report.update(workspace_id=ws, project_id=project)
        uploaded = []
        for fixture in manifest["fixtures"]:
            source = fixtures / fixture["file"]
            assert hashlib.sha256(source.read_bytes()).hexdigest() == fixture["sha256"]
            started = time.perf_counter()
            start_ns = time.time_ns()
            with source.open("rb") as file:
                asset = post(
                    base + f"/projects/{project}/upload",
                    params={"filename": source.name},
                    content=file,
                    headers={"Content-Length": str(source.stat().st_size)},
                )["asset_id"]
            uploaded.append((fixture, asset, started, start_ns))
        for fixture, asset, started, start_ns in uploaded:
            while time.perf_counter() - started < 1800:
                response = client.get(base + "/jobs", params={"project_id": project})
                response.raise_for_status()
                job = next((j for j in response.json() if j["asset_id"] == asset), None)
                if job and job["state"] in {"ready", "partial", "failed", "canceled"}:
                    break
                time.sleep(0.1)
            assert job and job["state"] in {"ready", "partial"}, job
            duration = time.perf_counter() - started
            observations = client.get(base + f"/assets/{asset}/observations").json()
            assert observations["total"] > 0, observations
            report["runs"].append(
                {
                    "asset_id": asset,
                    "job_id": job["id"],
                    "fixture": fixture["file"],
                    "started_ns": start_ns,
                    "ended_ns": time.time_ns(),
                    "time_to_searchable_seconds": duration,
                    "media_minutes_per_wall_minute": fixture["duration_seconds"] / duration,
                    "state": job["state"],
                    "observations": observations,
                }
            )
            save()
            print(label, fixture["file"], round(duration, 3), flush=True)
        report["corpus_wall_seconds"] = (
            max(r["ended_ns"] for r in report["runs"]) / 1e9
            - min(r["started_ns"] for r in report["runs"]) / 1e9
        )
        report["corpus_media_minutes_per_wall_minute"] = (
            sum(f["duration_seconds"] for f in manifest["fixtures"]) / report["corpus_wall_seconds"]
        )
        for repeat in range(5):
            for query in QUERIES:
                start = time.perf_counter()
                response = client.get(base + f"/projects/{project}/search", params={"q": query})
                response.raise_for_status()
                body = response.json()
                assert body["results"], body
                report["queries"].append(
                    {
                        "query": query,
                        "repeat": repeat,
                        "seconds": time.perf_counter() - start,
                        "mode": body["mode"],
                        "results": len(body["results"]),
                    }
                )
        values = [q["seconds"] for q in report["queries"]]
        report["query_p50_seconds"] = percentile(values, 0.5)
        report["query_p95_seconds"] = percentile(values, 0.95)
        # Export is a distinct operation, excluded from time-to-searchable.
        started = time.perf_counter()
        export = post(
            base + f"/projects/{project}/export-preview",
            json={
                "kind": "clips",
                "asset_id": report["runs"][-1]["asset_id"],
                "start_us": 1000000,
                "end_us": 4000000,
            },
        )
        post(base + f"/exports/{export['id']}/start")
        while time.perf_counter() - started < 600:
            jobs = client.get(base + "/jobs", params={"project_id": project}).json()
            job = next(j for j in jobs if j["workflow_id"] == f"export:{export['id']}")
            if job["state"] in {"completed", "failed"}:
                break
            time.sleep(0.1)
        assert job["state"] == "completed", job
        report["export"] = {
            "seconds": time.perf_counter() - started,
            "job_id": job["id"],
            "id": export["id"],
        }
        save()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--fixtures", type=Path, default=Path(".local/pipeline-study/fixtures"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    run(args.origin, args.fixtures, args.output, args.label)
