import json
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError
from rushes import activities, exports, routes_exports
from rushes.config import settings
from rushes.db import tenant_session
from rushes.models import (
    AnalysisRun,
    AnalysisWindow,
    Asset,
    Export,
    Job,
    MediaTimeline,
    Observation,
    Project,
)
from rushes.organization import (
    ORGANIZATION_SCHEMA_VERSION,
    ORGANIZATION_VERSION,
    category_asset_ids,
    category_records,
)
from rushes.routes_exports import ExportInput
from rushes.storage import StorageError, fingerprint
from sqlalchemy import select


@pytest.mark.parametrize(
    "extra",
    [
        {"category": "../nature"},
        {"category": "Nature"},
        {"category": "nature/water"},
        {"category": ""},
        {"category": "a" * 37},
        {"asset_id": str(uuid.uuid4())},
        {"collection_id": str(uuid.uuid4())},
        {"start_us": 0},
        {"end_us": 100},
        {"kind": "clips"},
        {"kind": "json"},
    ],
)
def test_category_export_input_rejects_unsafe_or_ambiguous_selection(extra):
    with pytest.raises(ValidationError):
        ExportInput.model_validate({"kind": "copies", "category": "nature", **extra})
    assert ExportInput(kind="copies", category="nature-water").category == "nature-water"


@pytest.mark.parametrize(
    "filename",
    [
        "../escape",
        "/escape",
        "nature/../../escape",
        "nature/./file",
        "nature//file",
        "nature\\file",
        ".",
        "",
    ],
)
def test_nested_export_paths_reject_traversal(tmp_path, filename):
    with pytest.raises(StorageError, match="output folder"):
        exports.media_output_path(tmp_path / "export", filename)


def test_nested_copy_receipt_reuses_relative_path_and_preserves_source(tmp_path, monkeypatch):
    monkeypatch.setattr(settings(), "min_free_bytes", 0)
    source = tmp_path / "original.mov"
    source.write_bytes(b"original camera bytes" * 100)
    original_stat = source.stat()
    with source.open("rb") as file:
        expected = fingerprint(file)
    entry = {
        "asset_id": str(uuid.uuid4()),
        "source_name": source.name,
        "source_root": str(tmp_path),
        "relative_path": source.name,
        "fingerprint": expected,
        "filename": "nature/0001-original.mov",
        "mode": "copy",
        "estimated_bytes": original_stat.st_size,
        "organization": {
            "version": ORGANIZATION_VERSION,
            "category_id": "nature",
            "evidence": [{"observation_id": "frozen-evidence", "version": 2}],
        },
    }
    key, group = next(iter(exports.source_groups([entry])))
    folder = tmp_path / "export"
    first = exports.write_media_group(key, group, folder)
    output = folder / first[0]["output"]
    modified = output.stat().st_mtime_ns
    assert first[0]["output"] == "nature/0001-original.mov"
    assert output.read_bytes() == source.read_bytes()
    assert first[0]["organization"] == entry["organization"]
    assert json.loads((folder / "nature/0001-original.mov.receipt.json").read_text()) == first[0]
    assert exports.write_media_group(key, group, folder) == first
    assert output.stat().st_mtime_ns == modified
    assert source.stat().st_mtime_ns == original_stat.st_mtime_ns
    source.write_bytes(b"changed source")
    with pytest.raises(StorageError, match="Source contents changed"):
        exports.write_media_group(key, group, folder)


@pytest.mark.parametrize(
    "link",
    [
        "nature",
        "nature/0001-source.mov",
        "nature/0001-source.mov.partial",
        "nature/0001-source.mov.receipt.json",
    ],
)
def test_nested_copy_rejects_symlink_destinations(tmp_path, monkeypatch, link):
    monkeypatch.setattr(settings(), "min_free_bytes", 0)
    folder, outside = tmp_path / "export", tmp_path / "outside"
    folder.mkdir()
    outside.mkdir()
    target = outside if link == "nature" else outside / "protected"
    if target != outside:
        target.write_bytes(b"untouched")
        (folder / "nature").mkdir()
    (folder / link).symlink_to(target, target_is_directory=target.is_dir())
    source = tmp_path / "source.mov"
    source.write_bytes(b"original")
    entry = {"filename": "nature/0001-source.mov", "mode": "copy", "estimated_bytes": 8}
    with source.open("rb") as file, pytest.raises(StorageError, match="output folder"):
        exports.write_media_entry(entry, folder, file)
    if target != outside:
        assert target.read_bytes() == b"untouched"


async def organize(db, asset, category="Nature"):
    timeline = await db.scalar(select(MediaTimeline).where(MediaTimeline.asset_id == asset.id))
    run = AnalysisRun(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        operation_key=str(uuid.uuid4()),
        model="synthetic",
        prompt_version="test",
        preprocessing_version="test",
        schema_version=ORGANIZATION_SCHEMA_VERSION,
        transcript_version="test",
        sampling={},
        status="completed",
    )
    db.add(run)
    await db.flush()
    window = AnalysisWindow(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        run_id=run.id,
        start_us=0,
        end_us=1_000_000,
        cache_key=str(uuid.uuid4()),
        state="completed",
    )
    db.add(window)
    await db.flush()
    observation = Observation(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        timeline_id=timeline.id,
        run_id=run.id,
        window_id=window.id,
        operation_key=str(uuid.uuid4()),
        kind="visual",
        start_us=0,
        end_us=1_000_000,
        proposed_start_us=0,
        proposed_end_us=1_000_000,
        description="Trees by the water",
        producer="synthetic",
        model="synthetic",
        prompt_version="test",
        preprocessing_version="test",
        attributes={
            "organization_version": ORGANIZATION_VERSION,
            "categories": category_records([category]),
        },
        evidence=[{"frame": 0}],
    )
    db.add(observation)
    await db.flush()
    return observation.id


@pytest.mark.integration
async def test_category_preview_freezes_full_files_and_evidence_then_exports(
    authenticated, tmp_path, monkeypatch
):
    clients, ws, _other, project, asset_id, _tokens = authenticated
    owner, viewer, outsider = clients
    monkeypatch.setattr(settings(), "output_root", tmp_path / "outputs")
    monkeypatch.setattr(settings(), "min_free_bytes", 0)
    monkeypatch.setattr(activities, "heartbeat", lambda *_: None)
    monkeypatch.setattr(exports, "heartbeat", lambda *_: None)
    source = tmp_path / "second-source.mov"
    source.write_bytes(b"second original")
    monkeypatch.setattr(settings(), "source_roots", [*settings().source_roots, tmp_path])
    async with tenant_session(ws) as db:
        first = await db.get(Asset, asset_id)
        original = Path(first.source_root) / first.relative_path
        with original.open("rb") as file:
            first.fingerprint = fingerprint(file)
        first.source_size = original.stat().st_size
        observation_id = await organize(db, first)
        original_observation = await db.get(Observation, observation_id)
        for index in range(1, 26):
            db.add(
                Observation(
                    workspace_id=ws,
                    asset_id=asset_id,
                    timeline_id=original_observation.timeline_id,
                    run_id=original_observation.run_id,
                    window_id=original_observation.window_id,
                    operation_key=str(uuid.uuid4()),
                    kind="visual",
                    start_us=index * 1000,
                    end_us=index * 1000 + 1000,
                    proposed_start_us=index * 1000,
                    proposed_end_us=index * 1000 + 1000,
                    description=f"Supporting trees {index}",
                    producer="synthetic",
                    model="synthetic",
                    prompt_version="test",
                    preprocessing_version="test",
                    attributes=original_observation.attributes,
                )
            )
        other_project = Project(workspace_id=ws, name="Another project")
        db.add(other_project)
        await db.flush()
        matching_ids = {asset_id}
        for project_id in (project, other_project.id):
            with source.open("rb") as file:
                expected = fingerprint(file)
            asset = Asset(
                workspace_id=ws,
                project_id=project_id,
                name=first.name,
                source_root=str(tmp_path),
                relative_path=source.name,
                fingerprint=expected,
                source_size=source.stat().st_size,
                duration_us=5_000_000,
                status="completed",
            )
            db.add(asset)
            await db.flush()
            db.add(
                MediaTimeline(
                    workspace_id=ws,
                    asset_id=asset.id,
                    kind="source",
                    details={"duration_us": asset.duration_us},
                )
            )
            await db.flush()
            await organize(db, asset)
            if project_id == project:
                matching_ids.add(asset.id)
    url = f"/api/workspaces/{ws}/projects/{project}/export-preview"
    body = {"kind": "copies", "category": "nature"}
    assert (await viewer.post(url, json=body)).status_code == 403
    assert (await outsider.post(url, json=body)).status_code == 404
    assert (await owner.post(url, json={**body, "category": "missing-category"})).status_code == 422
    response = await owner.post(url, json=body)
    assert response.status_code == 201, response.text
    preview = response.json()
    assert {uuid.UUID(entry["asset_id"]) for entry in preview["entries"]} == matching_ids
    assert len({entry["filename"] for entry in preview["entries"]}) == 2
    assert all(
        entry["filename"].startswith("nature/000") and entry["start_us"] == 0
        for entry in preview["entries"]
    )
    assert sorted(entry["end_us"] for entry in preview["entries"]) == [5_000_000, 10_000_000]
    assert "byte for byte" in preview["notice"] and "unmodified" in preview["notice"]
    export_id = uuid.UUID(preview["id"])
    async with tenant_session(ws) as db:
        output = await db.get(Export, export_id)
        job_id = output.job_id
        assert output.state == "draft" and (await db.get(Job, job_id)).state == "draft"
        frozen = next(
            entry["organization"]
            for entry in output.plan["entries"]
            if entry["asset_id"] == str(asset_id)
        )
        assert frozen["evidence"][0]["observation_id"] == str(observation_id)
        assert len(frozen["evidence"]) == 20
        assert frozen["evidence_count"] == 26 and frozen["evidence_truncated"] is True
        for observation in await db.scalars(
            select(Observation).where(Observation.asset_id == asset_id)
        ):
            observation.description = "Changed after preview"
            observation.attributes = {
                "organization_version": ORGANIZATION_VERSION,
                "categories": category_records(["Buildings"]),
            }
            observation.version += 1
        await db.flush()
        assert asset_id not in await category_asset_ids(db, ws, project, "nature")
    start = f"/api/workspaces/{ws}/exports/{export_id}/start"
    assert (await viewer.post(start)).status_code == 403
    assert (await owner.post(start)).status_code == 202
    list_url = f"/api/workspaces/{ws}/projects/{project}/exports"
    queued = await viewer.get(list_url)
    assert queued.status_code == 200, queued.text
    assert queued.json()["items"][0]["provenance"] == {"outputs": []}
    args = {"workspace_id": str(ws), "job_id": str(job_id)}
    assert (await exports.render_export(args))["state"] == "completed"
    async with tenant_session(ws) as db:
        output = await db.get(Export, export_id)
        assert output.provenance["organization"]["category_id"] == "nature"
        manifest = json.loads(
            (exports.export_folder(ws, export_id) / "provenance.json").read_text()
        )
        assert manifest["outputs"] == output.provenance["outputs"]
        evidence = next(
            row["organization"] for row in manifest["outputs"] if row["asset_id"] == str(asset_id)
        )
        assert evidence == frozen and evidence["evidence"][0]["description"] == "Trees by the water"
        paths = [row["output"] for row in output.provenance["outputs"]]
    listing = await viewer.get(list_url)
    assert listing.status_code == 200, listing.text
    assert listing.json()["total"] == 1
    listed_export = listing.json()["items"][0]
    assert listed_export["id"] == str(export_id) and listed_export["state"] == "completed"
    assert "plan" not in listed_export
    assert listed_export["provenance"] == {
        "outputs": [{"output": row["output"], "bytes": row["bytes"]} for row in manifest["outputs"]]
    }
    assert "Trees by the water" not in listing.text
    assert "evidence_count" not in listing.text
    for index, relative in enumerate(paths):
        download = f"/api/workspaces/{ws}/exports/{export_id}/download/{index}"
        assert (await outsider.get(download)).status_code == 404
        response = await viewer.get(download)
        assert response.status_code == 200
        assert response.content == (exports.export_folder(ws, export_id) / relative).read_bytes()
    async with tenant_session(ws) as db:
        output = await db.get(Export, export_id)
        assert output.provenance["outputs"] == manifest["outputs"]
        output.provenance = {"outputs": [{"output": "../outside.mov"}]}
    assert (
        await owner.get(f"/api/workspaces/{ws}/exports/{export_id}/download/0")
    ).status_code == 404


@pytest.mark.integration
async def test_category_export_enforces_file_limit_before_creating_draft(
    authenticated, monkeypatch
):
    clients, ws, _other, project, _asset, _tokens = authenticated

    async def oversized(*_args, **_kwargs):
        return [uuid.uuid4() for _ in range(501)]

    monkeypatch.setattr(routes_exports, "category_asset_ids", oversized)
    response = await clients[0].post(
        f"/api/workspaces/{ws}/projects/{project}/export-preview",
        json={"kind": "copies", "category": "nature"},
    )
    assert response.status_code == 422 and "500" in response.text
    async with tenant_session(ws) as db:
        assert not list(await db.scalars(select(Export).where(Export.project_id == project)))
