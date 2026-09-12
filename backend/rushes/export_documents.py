"""Synchronous document writers, called through the activity's storage thread guard."""

import csv
import json
import os

from rushes.config import settings
from rushes.storage import require_space, sync_file

WORKLOG_FIELDS = [
    "observation_id",
    "asset_id",
    "source_name",
    "source_relative_path",
    "import_relative_path",
    "source_sha256",
    "start_us",
    "end_us",
    "proposed_start_us",
    "proposed_end_us",
    "kind",
    "description",
    "producer",
    "model",
    "prompt_version",
    "preprocessing_version",
    "review_status",
    "source_timecode",
    "time_base",
    "timeline_id",
    "run_id",
    "window_id",
    "attributes",
    "evidence",
    "uncertainty",
    "version",
]


def csv_safe(value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value)
    if isinstance(value, str) and value.lstrip(" \t\r\n\ufeff").startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def publish_document(temporary, target):
    os.replace(temporary, target)
    return {"output": target.name, "bytes": target.stat().st_size}


def write_document(target, data):
    temporary = target.with_suffix(".partial")
    with temporary.open("wb") as file:
        file.write(data)
        sync_file(file)
    return publish_document(temporary, target)


def write_selections(target, kind, rows):
    temporary = target.with_suffix(".partial")
    with temporary.open("w", newline="") as file:
        if kind == "selections_json":
            json.dump(
                {
                    "schema": "rushes-selections-v1",
                    "interval_convention": "half-open source elapsed microseconds",
                    "selections": rows,
                },
                file,
                indent=2,
            )
        else:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows({key: csv_safe(value) for key, value in row.items()} for row in rows)
        sync_file(file)
    return publish_document(temporary, target)


def start_worklog(temporary, kind):
    with temporary.open("w", newline="") as file:
        if kind == "json":
            file.write(
                '{"schema":"rushes-worklog-v1","interval_convention":"half-open source elapsed microseconds","observations":['
            )
        else:
            csv.DictWriter(file, fieldnames=WORKLOG_FIELDS).writeheader()


def append_worklog(temporary, kind, records, first):
    with temporary.open("a", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=WORKLOG_FIELDS)
        for observation, asset, timeline in records:
            row = {
                key: getattr(observation, key)
                for key in WORKLOG_FIELDS
                if hasattr(observation, key)
            }
            row.update(
                observation_id=str(observation.id),
                asset_id=str(asset.id),
                source_name=asset.name,
                source_relative_path=asset.relative_path,
                import_relative_path=asset.import_relative_path,
                source_sha256=asset.fingerprint,
                source_timecode=timeline.details.get("source_timecode"),
                time_base=timeline.details["time_base"],
            )
            if kind == "json":
                file.write(("" if first else ",") + json.dumps(row, default=str))
            else:
                writer.writerow({key: csv_safe(value) for key, value in row.items()})
            require_space(temporary.parent, 0, settings().min_free_bytes)
            first = False


def finish_worklog(temporary, target, kind):
    with temporary.open("a") as file:
        if kind == "json":
            file.write("]}")
        sync_file(file)
    return publish_document(temporary, target)
