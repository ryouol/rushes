import shutil
import subprocess
import uuid

import pytest
from rushes.db import tenant_session
from rushes.models import Asset, MediaTimeline, Observation, Project, Usage
from rushes.pipeline import prepare_asset, transcribe_asset
from sqlalchemy import func, select


@pytest.mark.media
@pytest.mark.integration
async def test_persisted_media_slice_and_retry_preserves_user_correction(
    account_workspace, tmp_path, monkeypatch
):
    from rushes.config import settings

    if shutil.which("say") is None:
        pytest.skip("Synthetic speech fixture requires macOS say; supply WAV on other systems")
    speech = tmp_path / "synthetic-speech.aiff"
    subprocess.run(
        [
            "say",
            "-o",
            str(speech),
            "This is a synthetic timing fixture. The red notebook is beside the blue cup.",
        ],
        check=True,
    )
    source = tmp_path / "synthetic-speech.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:size=320x180:rate=24",
            "-i",
            str(speech),
            "-shortest",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
    )
    async with tenant_session(account_workspace) as db:
        project = Project(workspace_id=account_workspace, name="Synthetic speech verification")
        db.add(project)
        await db.flush()
        asset = Asset(
            workspace_id=account_workspace,
            project_id=project.id,
            name=source.name,
            source_root=str(tmp_path),
            relative_path=source.name,
        )
        db.add(asset)
        await db.flush()
        asset_id = str(asset.id)
    monkeypatch.setattr(settings(), "source_roots", [tmp_path])
    original_storage = settings().storage_root
    settings().storage_root = tmp_path / "artifacts"
    try:
        first = await prepare_asset(str(account_workspace), asset_id)
        assert first["has_audio"]
        assert first["duration_us"] > 1_000_000
        assert await prepare_asset(str(account_workspace), asset_id) == first
        result = await transcribe_asset(str(account_workspace), asset_id)
        assert result["segments"] >= 1
        async with tenant_session(account_workspace) as db:
            rows = list(
                await db.scalars(
                    select(Observation).where(Observation.asset_id == uuid.UUID(asset_id))
                )
            )
            assert any("synthetic" in row.description.lower() for row in rows)
            count = len(rows)
            corrected_id = rows[0].id
            rows[0].description = "Human correction must survive retries"
            rows[0].review_status = "corrected"
        monkeypatch.setattr("rushes.pipeline.PREPROCESSING_VERSION", "synthetic-video-recipe-next")
        await transcribe_asset(str(account_workspace), asset_id)
        async with tenant_session(account_workspace) as db:
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(Observation)
                    .where(Observation.asset_id == uuid.UUID(asset_id))
                )
                == count
            )
            assert (
                await db.get(Observation, corrected_id)
            ).description == "Human correction must survive retries"
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(MediaTimeline)
                    .where(MediaTimeline.asset_id == uuid.UUID(asset_id))
                )
                == 2
            )
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(Usage)
                    .where(Usage.asset_id == uuid.UUID(asset_id), Usage.kind == "source")
                )
                == 1
            )
    finally:
        settings().storage_root = original_storage
