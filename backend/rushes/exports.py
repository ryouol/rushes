import asyncio
import csv
import json
import os
import re
from pathlib import Path, PurePosixPath
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from temporalio import activity

from rushes.activities import heartbeat, keep_alive, stage
from rushes.config import settings
from rushes.db import tenant_session
from rushes.interchange import fcp7_xml, fcpxml
from rushes.media import RENDERER_VERSION, Timeline, render_clip
from rushes.models import Asset, Export, Job, MediaTimeline, Observation, Usage
from rushes.storage import (
    StorageError,
    authorized_source_root,
    fingerprint,
    open_source,
    require_space,
    run_storage_thread,
    storage_activity,
)
from rushes.timing import Interval


def safe_name(name: str) -> str:
    return re.sub(r"[^\w.-]+", "_", Path(name).stem).strip("._")[:100] or "footage"


def csv_safe(value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value)
    if isinstance(value, str) and value.lstrip(" \t\r\n\ufeff").startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_folder(workspace_id: UUID | str, export_id: UUID | str) -> Path:
    return settings().output_root / str(UUID(str(workspace_id))) / str(UUID(str(export_id)))


def media_output_path(folder: Path, filename: str) -> Path:
    relative = PurePosixPath(filename)
    if (
        not filename
        or not relative.parts
        or "\\" in filename
        or relative.is_absolute()
        or relative.as_posix() != filename
        or any(part in {".", ".."} for part in relative.parts)
    ):
        raise StorageError("Export output must stay within its output folder")
    root = folder.resolve()
    final = root.joinpath(*relative.parts)
    if not final.resolve().is_relative_to(root) or any(
        path.is_symlink()
        for path in [final, *final.parents]
        if path != root and path.is_relative_to(root)
    ):
        raise StorageError("Export output must stay within its output folder without symlinks")
    return final


def write_media_entry(entry: dict, folder: Path, source, progress=None) -> dict:
    final = media_output_path(folder, entry["filename"])
    receipt = media_output_path(folder, entry["filename"] + ".receipt.json")
    temporary_receipt = media_output_path(folder, entry["filename"] + ".receipt.partial.json")
    try:
        result = json.loads(receipt.read_text())
        with final.open("rb") as file:
            if (
                result["output"] == entry["filename"]
                and fingerprint(file) == result["output_sha256"]
                and (entry["mode"] == "copy" or result.get("renderer_version") == RENDERER_VERSION)
            ):
                return result
    except (OSError, ValueError, KeyError):
        pass
    config = settings()
    require_space(folder, entry["estimated_bytes"], config.min_free_bytes)
    final.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    source.seek(0)
    before = os.fstat(source.fileno())
    if entry["mode"] == "copy":
        temporary = media_output_path(folder, entry["filename"] + ".partial")
        with temporary.open("wb") as output:
            while chunk := source.read(1024 * 1024):
                require_space(folder, len(chunk), config.min_free_bytes)
                output.write(chunk)
                if progress:
                    progress("Copying original into separate export folder")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, final)
        plan = {"render": "byte-for-byte copy", "source_sha256": entry["fingerprint"]}
    else:
        plan = render_clip(
            source,
            Timeline.model_validate(entry["timeline"]),
            Interval(start_us=entry["start_us"], end_us=entry["end_us"]),
            final,
            threads=config.media_threads,
            progress=progress,
        )
    after = os.fstat(source.fileno())
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        final.unlink(missing_ok=True)
        raise StorageError("Source changed during export; no completed output was recorded")
    with final.open("rb") as file:
        result = {
            "asset_id": entry["asset_id"],
            "source_name": entry["source_name"],
            "output": final.relative_to(folder.resolve()).as_posix(),
            "output_sha256": fingerprint(file),
            "bytes": final.stat().st_size,
            "render_plan": plan,
            "renderer_version": RENDERER_VERSION if entry["mode"] != "copy" else "byte-copy-v1",
            **({"organization": entry["organization"]} if "organization" in entry else {}),
        }
    temporary_receipt.write_text(json.dumps(result))
    os.replace(temporary_receipt, receipt)
    return result


def source_groups(entries):
    groups = {}
    for entry in entries:
        key = (entry["source_root"], entry["relative_path"], entry["fingerprint"])
        groups.setdefault(key, []).append(entry)
    return groups.items()


def write_media_group(key, entries, folder, progress=None):
    root, relative, expected = key
    with open_source(Path(root), relative) as source:
        if fingerprint(source) != expected:
            raise StorageError("Source contents changed. Relink or re-index before exporting.")
        results = [write_media_entry(entry, folder, source, progress) for entry in entries]
        # One pinned source descriptor serves every select; verify the whole source again
        # before accepting the group, even if a writer restored its original timestamps.
        if fingerprint(source) != expected:
            for entry in entries:
                final = media_output_path(folder, entry["filename"])
                final.unlink(missing_ok=True)
                final.with_suffix(final.suffix + ".receipt.json").unlink(missing_ok=True)
            raise StorageError("Source changed during export; no completed output was recorded")
    return results


def verify_sources(entries):
    for (root, relative, expected), _ in source_groups(entries):
        with open_source(Path(root), relative) as source:
            if fingerprint(source) != expected:
                raise StorageError("Source changed; interchange references must be reviewed")


@activity.defn(name="render_export")
@storage_activity
async def render_export(args: dict):
    heartbeat()
    await stage(args, "Rendering export into a separate output folder", 10)
    async with tenant_session(args["workspace_id"]) as db:
        export = await db.scalar(select(Export).where(Export.job_id == UUID(args["job_id"])))
        if export.state == "completed":
            return {"state": "completed", "export_id": str(export.id)}
        export.state = "running"
        export_id, kind, plan, project_id = export.id, export.kind, export.plan, export.project_id
        plan = {**plan, "entries": [dict(entry) for entry in plan["entries"]]}
        asset_ids = {UUID(entry["asset_id"]) for entry in plan["entries"]}
        assets = {
            asset.id: asset
            for asset in await db.scalars(
                select(Asset).where(Asset.id.in_(asset_ids), Asset.project_id == project_id)
            )
        }
        for entry in plan["entries"]:
            asset = assets.get(UUID(entry["asset_id"]))
            if asset is None or asset.fingerprint != entry["fingerprint"]:
                raise StorageError("The reviewed source changed. Create a new export preview.")
            entry["source_root"] = str(
                authorized_source_root(asset.source_root, asset.workspace_id, asset.id)
            )
            entry["relative_path"] = asset.relative_path
            entry["import_relative_path"] = asset.import_relative_path
    folder = export_folder(args["workspace_id"], export_id)
    require_space(folder, plan["estimated_bytes"], settings().min_free_bytes)
    outputs = []
    if kind in {"clips", "copies"}:
        filenames = [entry["filename"] for entry in plan["entries"]]
        if len(filenames) != len(set(filenames)):
            raise StorageError("Export outputs contain duplicate filenames; review a new preview")
        for filename in filenames:
            media_output_path(folder, filename)
        for key, entries in source_groups(plan["entries"]):
            outputs.extend(
                await keep_alive(
                    run_storage_thread(write_media_group, key, entries, folder, heartbeat)
                )
            )
            await stage(
                args,
                f"Exported {len(outputs)} of {len(plan['entries'])} items",
                round(90 * len(outputs) / len(plan["entries"])),
            )
        order = {entry["filename"]: index for index, entry in enumerate(plan["entries"])}
        outputs.sort(key=lambda output: order[output["output"]])
        manifest = folder / "provenance.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema": "rushes-export-v1",
                    "outputs": outputs,
                    **({"organization": plan["organization"]} if "organization" in plan else {}),
                },
                indent=2,
            )
        )
        output_path = str(folder)
    elif kind in {"selections_json", "selections_csv"}:
        rows = [
            {
                "asset_id": entry["asset_id"],
                "source_name": entry["source_name"],
                "relative_path": entry["relative_path"],
                "import_relative_path": entry.get("import_relative_path"),
                "source_sha256": entry["fingerprint"],
                "start_us": entry["start_us"],
                "end_us": entry["end_us"],
                "source_timecode": entry["timeline"].get("source_timecode"),
                "source_time_base": entry["timeline"]["time_base"],
            }
            for entry in plan["entries"]
        ]
        target = folder / ("selections.json" if kind == "selections_json" else "selections.csv")
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
                writer.writerows(
                    {key: csv_safe(value) for key, value in row.items()} for row in rows
                )
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, target)
        output_path = str(target)
        outputs = [{"output": target.name, "bytes": target.stat().st_size}]
    elif kind in {"fcp7xml", "fcpxml"}:
        target = folder / ("selects.xml" if kind == "fcp7xml" else "selects.fcpxml")
        await keep_alive(run_storage_thread(verify_sources, plan["entries"]))
        writer = fcp7_xml if kind == "fcp7xml" else fcpxml
        data = await keep_alive(run_storage_thread(writer, plan["entries"], "RUSHES selects"))
        temporary = target.with_suffix(".partial")
        temporary.write_bytes(data)
        os.replace(temporary, target)
        output_path = str(target)
        outputs = [
            {
                "output": target.name,
                "bytes": target.stat().st_size,
                "validation": "XML structure only; target-editor round trip needs input",
            }
        ]
    else:
        filename = "worklog.json" if kind == "json" else "worklog.csv"
        target = folder / filename
        temporary = target.with_suffix(".partial")
        async with tenant_session(args["workspace_id"]) as db:
            query = (
                select(Observation, Asset, MediaTimeline)
                .join(Asset, Asset.id == Observation.asset_id)
                .join(MediaTimeline, MediaTimeline.id == Observation.timeline_id)
                .where(Asset.project_id == project_id)
            )
            rows = await db.stream(
                query.order_by(Asset.id, Observation.start_us).execution_options(yield_per=200)
            )
            with temporary.open("w", newline="") as file:
                if kind == "json":
                    file.write(
                        '{"schema":"rushes-worklog-v1","interval_convention":"half-open source elapsed microseconds","observations":['
                    )
                first = True
                fields = [
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
                writer = csv.DictWriter(file, fieldnames=fields)
                if kind == "csv":
                    writer.writeheader()
                async for observation, asset, timeline in rows:
                    row = {
                        key: getattr(observation, key)
                        for key in fields
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
                        # Spreadsheet consumers must not evaluate transcript/OCR text as formulas.
                        writer.writerow({key: csv_safe(value) for key, value in row.items()})
                    require_space(folder, 0, settings().min_free_bytes)
                    first = False
                    heartbeat("Writing worklog export")
                if kind == "json":
                    file.write("]}")
        os.replace(temporary, target)
        output_path = str(target)
        outputs = [{"output": target.name, "bytes": target.stat().st_size}]
    async with tenant_session(args["workspace_id"]) as db:
        job = await db.scalar(select(Job).where(Job.id == UUID(args["job_id"])).with_for_update())
        if job.state in {"failed", "canceled", "cancel_requested"}:
            raise asyncio.CancelledError()
        export = await db.get(Export, export_id)
        export.output_path, export.state, export.provenance = (
            output_path,
            "completed",
            {
                "outputs": outputs,
                **({"organization": plan["organization"]} if "organization" in plan else {}),
            },
        )
        job.state, job.stage, job.progress = "completed", "Export complete", 100
        await db.execute(
            insert(Usage)
            .values(
                workspace_id=job.workspace_id,
                operation_key=f"export:{export_id}",
                kind="render" if kind == "clips" else "export",
                duration_us=sum(
                    entry.get("end_us", 0) - entry.get("start_us", 0)
                    for entry in plan.get("entries", [])
                ),
                bytes=sum(output["bytes"] for output in outputs),
            )
            .on_conflict_do_nothing()
        )
    return {"state": "completed", "export_id": str(export_id)}
