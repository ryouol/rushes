"""Summarize measured spans without double-counting nested stages."""

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def summarize(root, reports):
    traces = rows(root / "trace.jsonl")
    result = []
    for path in reports:
        report = json.loads(path.read_text())
        memory = rows(path.with_name(path.stem + "-memory.jsonl"))
        jobs = {run["job_id"] for run in report["runs"]}
        ends = [r for r in traces if r["event"] == "end" and r.get("job_id") in jobs]
        stage = defaultdict(float)
        queue = defaultdict(float)
        for row in ends:
            if row["name"].startswith("activity."):
                stage[row["name"]] += row["duration_ns"] / 1e9
                queue[row["name"]] += row["queue_wait_ns"] / 1e9
        begin = min(r["started_ns"] for r in report["runs"])
        finish = max(r["ended_ns"] for r in report["runs"])
        memory = [r for r in memory if begin <= r["time_ns"] <= finish]

        def peak(name, aggregate=False, samples=memory):
            return max(
                (
                    sum(p["rss_bytes"] for p in r["processes"] if p["name"] == name)
                    if aggregate
                    else max(
                        (p["rss_bytes"] for p in r["processes"] if p["name"] == name), default=0
                    )
                    for r in samples
                ),
                default=0,
            )

        transcripts = []
        for run in report["runs"]:
            items = run["observations"]["items"]
            fixture = next(f for f in report["fixtures"]["fixtures"] if f["file"] == run["fixture"])
            assert len(items) == run["observations"]["total"], (
                "Fetch all observations before checking correctness"
            )
            assert all(
                0 <= x["start_us"] < x["end_us"] <= fixture["duration_seconds"] * 1000000
                for x in items
            )
            normalized = sorted(
                [
                    {k: x[k] for k in ["start_us", "end_us", "description", "attributes"]}
                    for x in items
                ],
                key=lambda x: (x["start_us"], x["end_us"], x["description"]),
            )
            transcripts.append(
                {
                    "fixture": run["fixture"],
                    "segments": len(items),
                    "sha256": hashlib.sha256(
                        json.dumps(normalized, sort_keys=True).encode()
                    ).hexdigest(),
                }
            )
        export = report["export"]
        export_spans = [
            r
            for r in traces
            if r["event"] == "end"
            and r.get("job_id") == export["job_id"]
            and r["name"] == "activity.render_export"
        ]
        output = next((root / "exports" / report["workspace_id"] / export["id"]).glob("*.mp4"))
        result.append(
            {
                "label": report["label"],
                "corpus_wall_seconds": report["corpus_wall_seconds"],
                "media_minutes_per_wall_minute": report["corpus_media_minutes_per_wall_minute"],
                "time_to_searchable_seconds": [
                    r["time_to_searchable_seconds"] for r in report["runs"]
                ],
                "activity_execution_seconds": dict(stage),
                "activity_queue_seconds": dict(queue),
                "retry_attempts": sum(
                    r["attempt"] > 1 for r in ends if r["name"].startswith("activity.")
                ),
                "peak_container_bytes": max(r["container_bytes"] for r in memory),
                "peak_individual_ffmpeg_rss_bytes": peak("ffmpeg"),
                "peak_aggregate_ffmpeg_rss_bytes": peak("ffmpeg", True),
                "memory_samples": len(memory),
                "query_p50_seconds": report["query_p50_seconds"],
                "query_p95_seconds": report["query_p95_seconds"],
                "query_count": len(report["queries"]),
                "query_modes": sorted({q["mode"] for q in report["queries"]}),
                "export_wall_seconds": export["seconds"],
                "export_activity_seconds": sum(r["duration_ns"] / 1e9 for r in export_spans),
                "export_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "export_bytes": output.stat().st_size,
                "transcript_bounds_valid": True,
                "transcripts": transcripts,
            }
        )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("reports", type=Path, nargs="+")
    args = parser.parse_args()
    args.output.write_text(json.dumps(summarize(args.root, args.reports), indent=2) + "\n")
