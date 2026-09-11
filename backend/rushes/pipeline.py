import hashlib
import json
import os
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from rushes.config import settings
from rushes.db import tenant_session
from rushes.inference import PREPROCESSING_VERSION, TRANSCRIPTION_PREPROCESSING_VERSION, transcribe
from rushes.media import (
    Timeline,
    detect_shots,
    extract_audio,
    inspect,
    make_proxy,
    proxy_mapping,
    render_clip,
    thumbnail,
)
from rushes.models import Asset, MediaTimeline, Observation, Shot, Usage
from rushes.storage import (
    StorageError,
    artifact_path,
    authorized_source_root,
    fingerprint,
    open_source,
    require_space,
    run_storage_thread,
)
from rushes.timing import Interval, bounded_windows


def asset_folder(workspace_id: str, asset_id: str) -> Path:
    folder = (
        artifact_path(settings().storage_root, workspace_id, asset_id, "manifest.json").parent
        / PREPROCESSING_VERSION
    )
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    return folder


def _prepare(
    workspace_id: str, asset_id: str, root: str, relative: str, progress=None, expected_digest=None
) -> dict:
    config = settings()
    folder = asset_folder(workspace_id, asset_id)
    manifest = folder / "manifest.json"
    with open_source(authorized_source_root(root, workspace_id, asset_id), relative) as source:
        before = os.fstat(source.fileno())
        digest = fingerprint(source)
        if expected_digest and digest != expected_digest:
            raise StorageError(
                "Source bytes changed. Relink matching footage or import the changed file as a new asset."
            )
        try:
            cached = json.loads(manifest.read_text())
            if cached["source_hash"] == digest and cached["preprocessing"] == PREPROCESSING_VERSION:
                for name, checksum in cached["artifacts"].items():
                    with (folder / name).open("rb") as artifact:
                        if fingerprint(artifact) != checksum:
                            raise ValueError("Artifact checksum changed")
                return cached
        except (OSError, ValueError, KeyError):
            pass
        require_space(folder, min(before.st_size, config.max_upload_bytes), config.min_free_bytes)
        original = inspect(
            source,
            folder / "source-frames.jsonl.gz",
            progress=progress,
            max_seconds=config.max_source_seconds,
        )
        proxy = folder / "proxy.mp4"
        make_proxy(source, proxy, original, threads=config.media_threads, progress=progress)
        with proxy.open("rb") as preview:
            preview_timeline = inspect(
                preview,
                folder / "proxy-frames.jsonl.gz",
                progress=progress,
                max_seconds=config.max_source_seconds,
            )
        mapping = proxy_mapping(original, preview_timeline)
        shots = detect_shots(proxy, original.duration_us, progress)
        thumbnail(proxy, folder / "thumbnail.jpg")
        after = os.fstat(source.fileno())
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise StorageError("Source changed during processing; reselect the stable source")
        artifacts = {}
        for name in [
            "proxy.mp4",
            "thumbnail.jpg",
            "source-frames.jsonl.gz",
            "proxy-frames.jsonl.gz",
        ]:
            with (folder / name).open("rb") as artifact:
                artifacts[name] = fingerprint(artifact)
        result = {
            "source_hash": digest,
            "size": before.st_size,
            "mtime_ns": before.st_mtime_ns,
            "preprocessing": PREPROCESSING_VERSION,
            "source": original.model_dump(),
            "proxy": preview_timeline.model_dump(),
            "mapping": mapping,
            "shots": [shot.model_dump() for shot in shots],
            "artifacts": artifacts,
        }
        temporary = manifest.with_suffix(".partial.json")
        temporary.write_text(json.dumps(result))
        os.replace(temporary, manifest)
        return result


async def prepare_asset(workspace_id: str, asset_id: str, progress=None) -> dict:
    async with tenant_session(workspace_id) as db:
        asset = await db.get(Asset, UUID(asset_id))
        if asset is None:
            raise ValueError("Asset not found")
        asset.status = "processing"
        root, relative, expected_digest = asset.source_root, asset.relative_path, asset.fingerprint
    result = await run_storage_thread(
        _prepare, workspace_id, asset_id, root, relative, progress, expected_digest
    )
    folder = asset_folder(workspace_id, asset_id)
    async with tenant_session(workspace_id) as db:
        asset = await db.get(Asset, UUID(asset_id))
        asset.fingerprint = result["source_hash"]
        asset.duplicate_of_id = await db.scalar(
            select(Asset.id)
            .where(
                Asset.fingerprint == result["source_hash"],
                Asset.id != asset.id,
                Asset.workspace_id == asset.workspace_id,
            )
            .order_by(Asset.created_at)
            .limit(1)
        )
        asset.source_size = result["size"]
        asset.source_mtime_ns = result["mtime_ns"]
        asset.duration_us = result["source"]["duration_us"]
        asset.proxy_path = str(folder / "proxy.mp4")
        asset.thumbnail_path = str(folder / "thumbnail.jpg")
        asset.status = "preview_ready"
        for kind in ["source", "proxy"]:
            statement = insert(MediaTimeline).values(
                workspace_id=UUID(workspace_id),
                asset_id=UUID(asset_id),
                kind=kind,
                details=result[kind],
                mapping=result["mapping"],
            )
            await db.execute(
                statement.on_conflict_do_update(
                    index_elements=["asset_id", "kind"],
                    set_={"details": result[kind], "mapping": result["mapping"]},
                )
            )
        for shot in result["shots"]:
            await db.execute(
                insert(Shot)
                .values(workspace_id=UUID(workspace_id), asset_id=UUID(asset_id), **shot)
                .on_conflict_do_nothing()
            )
        await db.execute(
            insert(Usage)
            .values(
                workspace_id=UUID(workspace_id),
                asset_id=UUID(asset_id),
                operation_key=f"source:{asset_id}",
                kind="source",
                duration_us=asset.duration_us,
                bytes=asset.source_size,
            )
            .on_conflict_do_nothing()
        )
    return {
        "asset_id": asset_id,
        "duration_us": result["source"]["duration_us"],
        "has_audio": result["source"]["has_audio"],
    }


def prepare_chunk(workspace_id: str, asset_id: str, window: Interval, progress=None) -> Path:
    folder = asset_folder(workspace_id, asset_id)
    manifest = json.loads((folder / "manifest.json").read_text())
    extracted = proxy_interval(manifest, window)
    path = folder / f"chunk-{window.start_us}-{window.end_us}.mp4"
    checksum_path = path.with_suffix(".sha256")
    try:
        expected = checksum_path.read_text()
        with path.open("rb") as file:
            timing = json.loads(path.with_suffix(".timing.json").read_text())
            if (
                fingerprint(file) == expected
                and timing.get("requested_source") == window.model_dump()
            ):
                return path
    except (OSError, ValueError, KeyError):
        pass
    require_space(folder, 64 * 1024**2, settings().min_free_bytes)
    with (folder / "proxy.mp4").open("rb") as proxy:
        plan = render_clip(
            proxy,
            Timeline.model_validate(manifest["proxy"]),
            extracted,
            path,
            threads=settings().media_threads,
            progress=progress,
        )
    plan.update(extraction_provenance(window, extracted))
    path.with_suffix(".timing.json").write_text(json.dumps(plan))
    with path.open("rb") as file:
        checksum_path.write_text(fingerprint(file))
    return path


def proxy_interval(manifest: dict, window: Interval) -> Interval:
    window.within(manifest["source"]["duration_us"])
    end = min(window.end_us, manifest["proxy"]["duration_us"])
    if window.start_us >= end:
        raise ValueError("Selected source interval has no proxy coverage")
    return Interval(start_us=window.start_us, end_us=end)


def extraction_provenance(requested: Interval, extracted: Interval) -> dict:
    return {
        "requested_source": requested.model_dump(),
        "extracted_proxy": extracted.model_dump(),
        "source_offset_us": extracted.start_us,
        "trimmed_tail_us": requested.end_us - extracted.end_us,
    }


async def ensure_prepared(workspace_id: str, asset_id: str, progress=None) -> dict:
    path = asset_folder(workspace_id, asset_id) / "manifest.json"
    try:
        return json.loads(await run_storage_thread(path.read_text))
    except FileNotFoundError:
        # A workflow may resume after prepare ran under a prior preprocessing version.
        await prepare_asset(workspace_id, asset_id, progress)
        return json.loads(await run_storage_thread(path.read_text))


def prepare_audio(workspace_id: str, asset_id: str, window: Interval, progress=None):
    folder = asset_folder(workspace_id, asset_id)
    manifest = json.loads((folder / "manifest.json").read_text())
    extracted = proxy_interval(manifest, window)
    output = folder / f"audio-{window.start_us}-{window.end_us}.wav"
    with (folder / "proxy.mp4").open("rb") as source:
        extract_audio(
            source, Timeline.model_validate(manifest["proxy"]), extracted, output, progress
        )
    return output


async def transcribe_asset(workspace_id: str, asset_id: str, progress=None) -> dict:
    folder = asset_folder(workspace_id, asset_id)
    manifest = await ensure_prepared(workspace_id, asset_id, progress)
    if not manifest["source"]["has_audio"]:
        return {"state": "no_audio", "segments": 0}
    timeline = Timeline.model_validate(manifest["source"])
    # Transcription has contiguous, non-overlapping windows to avoid duplicate customer text.
    windows = bounded_windows(timeline.duration_us, [], 60_000_000, overlap_us=0)
    count = 0
    async with tenant_session(workspace_id) as db:
        source_timeline = await db.scalar(
            select(MediaTimeline).where(
                MediaTimeline.asset_id == UUID(asset_id), MediaTimeline.kind == "source"
            )
        )
        timeline_id = source_timeline.id
    for index, window in enumerate(windows):
        cache_key = hashlib.sha256(
            json.dumps(
                {
                    "source": manifest["source_hash"],
                    "window": window.model_dump(),
                    "model": settings().transcription_model,
                    "preprocessing": TRANSCRIPTION_PREPROCESSING_VERSION,
                    "transcription": "faster-whisper-v1",
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        async with tenant_session(workspace_id) as db:
            completed = await db.scalar(
                select(Usage.id).where(
                    Usage.operation_key == f"transcription:{asset_id}:{cache_key}"
                )
            )
        if completed:
            continue
        extracted = proxy_interval(manifest, window)
        transcript_file = folder / f"transcript-{cache_key}.json"
        try:
            rows = json.loads(transcript_file.read_text())
        except (OSError, ValueError):
            chunk = await run_storage_thread(
                prepare_audio, workspace_id, asset_id, window, progress
            )
            try:
                rows = await run_storage_thread(transcribe, chunk, extracted)
            finally:
                chunk.unlink(missing_ok=True)
            temporary = transcript_file.with_suffix(".partial.json")
            temporary.write_text(json.dumps(rows))
            os.replace(temporary, transcript_file)
        async with tenant_session(workspace_id) as db:
            for number, row in enumerate(rows):
                await db.execute(
                    insert(Observation)
                    .values(
                        workspace_id=UUID(workspace_id),
                        asset_id=UUID(asset_id),
                        timeline_id=timeline_id,
                        operation_key=f"transcript:{asset_id}:{cache_key}:{number}",
                        kind="speech",
                        start_us=row["start_us"],
                        end_us=row["end_us"],
                        proposed_start_us=row["start_us"],
                        proposed_end_us=row["end_us"],
                        description=row["text"],
                        attributes={
                            "language": row["language"],
                            "words": row["words"],
                            "word_time_basis": "chunk-relative seconds",
                            "word_offset_us": window.start_us,
                        },
                        evidence=[
                            {
                                "artifact": transcript_file.name,
                                "window": window.model_dump(),
                                **extraction_provenance(window, extracted),
                            }
                        ],
                        producer="faster-whisper",
                        model=settings().transcription_model,
                        prompt_version="transcription-v1",
                        preprocessing_version=TRANSCRIPTION_PREPROCESSING_VERSION,
                        uncertainty="approximate transcription",
                    )
                    .on_conflict_do_nothing()
                )
            await db.execute(
                insert(Usage)
                .values(
                    workspace_id=UUID(workspace_id),
                    asset_id=UUID(asset_id),
                    operation_key=f"transcription:{asset_id}:{cache_key}",
                    kind="transcription",
                    duration_us=extracted.end_us - extracted.start_us,
                    model=settings().transcription_model,
                )
                .on_conflict_do_nothing()
            )
        count += len(rows)
        if progress:
            progress(f"Transcribed window {index + 1} of {len(windows)}")
    return {"state": "completed", "segments": count}
