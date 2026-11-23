import uuid
from types import SimpleNamespace

import pytest
from rushes import routes_settings
from rushes.config import settings
from rushes.db import tenant_session
from rushes.models import Asset, Project


async def ready_service(*args, **kwargs):
    return object()


@pytest.mark.parametrize("free, reserve, available", [(900, 200, 700), (200, 200, 0), (150, 200, 0)])
async def test_settings_reports_space_after_reserve(authenticated, monkeypatch, free, reserve, available):
    clients, workspace, *_ = authenticated
    config = settings()
    monkeypatch.setattr(config, "min_free_bytes", reserve)
    monkeypatch.setattr(routes_settings.Client, "connect", ready_service)
    monkeypatch.setattr(
        routes_settings.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(free=free if path == config.storage_root else 3000),
    )

    response = await clients[0].get(f"/api/workspaces/{workspace}/settings")

    assert response.status_code == 200
    data = response.json()
    assert data["disk_free_bytes"] == free
    assert data["minimum_free_bytes"] == reserve
    assert data["usable_storage_bytes"] == available
    assert data["export_disk_free_bytes"] == 3000
    assert data["export_usable_storage_bytes"] == 3000 - reserve
    assert data["temporal_connected"] is True
    assert data["export_storage_separate_volume"] == (
        config.storage_root.stat().st_dev != config.output_root.stat().st_dev
    )
    capacity = await clients[0].get(f"/api/workspaces/{workspace}/storage-capacity")
    assert capacity.status_code == 200
    assert capacity.json() == {
        "disk_free_bytes": free,
        "minimum_free_bytes": reserve,
        "usable_storage_bytes": available,
    }


async def test_storage_preflight_reads_current_capacity_without_workflow_or_export_checks(
    authenticated, monkeypatch
):
    clients, workspace, *_ = authenticated
    config = settings()
    free = 900
    checked_paths = []
    workflow_checks = []

    def disk_usage(path):
        checked_paths.append(path)
        assert path == config.storage_root
        return SimpleNamespace(free=free)

    async def workflow_unavailable(*args, **kwargs):
        workflow_checks.append(True)
        raise OSError("Synthetic workflow outage")

    monkeypatch.setattr(config, "min_free_bytes", 200)
    monkeypatch.setattr(routes_settings.shutil, "disk_usage", disk_usage)
    monkeypatch.setattr(routes_settings.Client, "connect", workflow_unavailable)
    endpoint = f"/api/workspaces/{workspace}/storage-capacity"
    # Read-only members retain the same capacity access as Settings.
    for client in clients[:2]:
        response = await client.get(endpoint)
        assert response.status_code == 200
        assert response.json() == {
            "disk_free_bytes": 900,
            "minimum_free_bytes": 200,
            "usable_storage_bytes": 700,
        }
    free = 150
    assert (await clients[0].get(endpoint)).json() == {
        "disk_free_bytes": 150,
        "minimum_free_bytes": 200,
        "usable_storage_bytes": 0,
    }
    assert checked_paths == [config.storage_root] * 3
    assert workflow_checks == []
    assert (await clients[2].get(endpoint)).status_code == 404
    # Unauthorized requests must not even read server capacity.
    clients[0].cookies.clear()
    assert (await clients[0].get(endpoint)).status_code == 401
    assert len(checked_paths) == 3
    # Settings still reports workflow health independently of upload preflight.
    monkeypatch.setattr(routes_settings.shutil, "disk_usage", lambda path: SimpleNamespace(free=free))
    health = await clients[1].get(f"/api/workspaces/{workspace}/settings")
    assert health.status_code == 200
    assert health.json()["temporal_connected"] is False
    assert workflow_checks == [True]


async def test_workspace_storage_counts_recorded_uploads_without_deduplicating_or_indexed_bytes(
    authenticated, monkeypatch
):
    clients, workspace, other_workspace, project, *_ = authenticated
    monkeypatch.setattr(routes_settings.Client, "connect", ready_service)
    async with tenant_session(workspace) as db:
        second_project = Project(workspace_id=workspace, name="Second storage project")
        db.add(second_project)
        await db.flush()
        for destination, kind, size in [
            (project, "uploaded", 250),
            (second_project.id, "uploaded", 250),
            (project, "indexed", 9000),
        ]:
            db.add(
                Asset(
                    workspace_id=workspace,
                    project_id=destination,
                    name="Recorded source.mp4",
                    source_root="/synthetic",
                    relative_path=str(uuid.uuid4()),
                    source_kind=kind,
                    source_size=size,
                    fingerprint="f" * 64,
                )
            )
    async with tenant_session(other_workspace) as db:
        other_project = Project(workspace_id=other_workspace, name="Other storage project")
        db.add(other_project)
        await db.flush()
        db.add(
            Asset(
                workspace_id=other_workspace,
                project_id=other_project.id,
                name="Other upload.mp4",
                source_root="/synthetic",
                relative_path=str(uuid.uuid4()),
                source_kind="uploaded",
                source_size=99999,
            )
        )

    # Both members can see the summary; unrelated workspace sources do not enter it.
    for client in clients[:2]:
        response = await client.get(f"/api/workspaces/{workspace}/settings")
        assert response.status_code == 200
        data = response.json()
        assert data["workspace_project_count"] == 2
        assert data["workspace_file_count"] == 4
        assert data["workspace_uploaded_file_count"] == 2
        assert data["workspace_uploaded_source_bytes"] == 500
    assert (await clients[2].get(f"/api/workspaces/{workspace}/settings")).status_code == 404
