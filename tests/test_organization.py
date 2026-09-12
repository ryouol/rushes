import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from rushes import activities
from rushes.config import settings
from rushes.db import tenant_session
from rushes.inference import (
    PREPROCESSING_VERSION,
    PROMPT_VERSION,
    SCHEMA_VERSION,
    AnalysisResponse,
    provider_response_schema,
)
from rushes.models import (
    AnalysisRun,
    AnalysisWindow,
    Asset,
    Job,
    MediaTimeline,
    Observation,
    Project,
    Usage,
)
from rushes.organization import (
    ORGANIZATION_VERSION,
    category_asset_ids,
    category_records,
)
from sqlalchemy import func, select


def proposal(categories=None):
    return {
        "kind": "visual_event",
        "description": "Waves break along a visible rocky coastline",
        "start_seconds": 0,
        "end_seconds": 1,
        "uncertainty": "low",
        **({"categories": categories} if categories is not None else {}),
    }


def test_semantic_categories_normalize_without_keyword_guessing():
    response = AnalysisResponse.model_validate(
        {"observations": [proposal([" coastLINE ", "COASTLINE", "Waves"])]}
    )
    assert response.observations[0].categories == ["Coastline", "Waves"]
    assert category_records(response.observations[0].categories) == [
        {"id": "coastline", "name": "Coastline"},
        {"id": "waves", "name": "Waves"},
    ]
    assert (
        AnalysisResponse.model_validate({"observations": [proposal([])]}).observations[0].categories
        == []
    )
    # Previously received evidence remains parseable, without generating labels from its text.
    assert (
        AnalysisResponse.model_validate({"observations": [proposal()]}).observations[0].categories
        == []
    )
    schema = provider_response_schema()["$defs"]["ProposedObservation"]
    assert "categories" in schema["required"]


@pytest.mark.parametrize(
    "categories",
    [
        ["A", "B", "C", "D"],
        ["x" * 37],
        [""],
        ["<script>"],
        ["../Coastline"],
        ["Coastline/Waves"],
        ["Coastline\\Waves"],
        ["Uncategorized"],
        ["海岸"],
        ["One two three four five six seven"],
        [12],
    ],
)
def test_invalid_category_labels_reject_the_response(categories):
    with pytest.raises(ValidationError):
        AnalysisResponse.model_validate({"observations": [proposal(categories)]})


async def make_asset(db, workspace, project, name="Other.mp4", status="ready"):
    asset = Asset(
        workspace_id=workspace,
        project_id=project,
        name=name,
        source_root="/synthetic",
        relative_path=str(uuid.uuid4()),
        duration_us=10_000_000,
        status=status,
    )
    db.add(asset)
    await db.flush()
    db.add(
        MediaTimeline(
            workspace_id=workspace,
            asset_id=asset.id,
            kind="source",
            details={"duration_us": asset.duration_us},
        )
    )
    await db.flush()
    return asset


async def make_run(
    db,
    asset,
    labels,
    *,
    state="ready",
    window_state="completed",
    schema=SCHEMA_VERSION,
    created_at=None,
):
    run = AnalysisRun(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        operation_key=str(uuid.uuid4()),
        model="synthetic-no-provider",
        prompt_version=PROMPT_VERSION,
        preprocessing_version=PREPROCESSING_VERSION,
        schema_version=schema,
        transcript_version="synthetic",
        sampling={},
        status=state,
        **({"created_at": created_at} if created_at else {}),
    )
    db.add(run)
    await db.flush()
    window = AnalysisWindow(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        run_id=run.id,
        start_us=0,
        end_us=10_000_000,
        cache_key=str(uuid.uuid4()),
        state=window_state,
    )
    db.add(window)
    await db.flush()
    timeline = await db.scalar(
        select(MediaTimeline).where(
            MediaTimeline.asset_id == asset.id, MediaTimeline.kind == "source"
        )
    )
    for names in labels:
        db.add(
            Observation(
                workspace_id=asset.workspace_id,
                asset_id=asset.id,
                timeline_id=timeline.id,
                run_id=run.id,
                window_id=window.id,
                operation_key=str(uuid.uuid4()),
                kind="visual_event",
                start_us=0,
                end_us=1_000_000,
                proposed_start_us=0,
                proposed_end_us=1_000_000,
                description="Synthetic visible evidence",
                attributes={
                    "organization_version": ORGANIZATION_VERSION,
                    "categories": category_records(names),
                },
                producer="gemini",
                model=run.model,
                prompt_version=run.prompt_version,
                preprocessing_version=run.preprocessing_version,
            )
        )
    await db.flush()
    return run, window


@pytest.mark.integration
async def test_categories_count_distinct_full_assets_and_filter_before_pagination(
    authenticated, monkeypatch
):
    clients, ws, _, project, asset_id, _ = authenticated
    monkeypatch.setattr(settings(), "gemini_api_key", None)
    async with tenant_session(ws) as db:
        first = await db.get(Asset, asset_id)
        await make_run(db, first, [["Coastline", "Waves"], ["Coastline"]])
        second = await make_asset(db, ws, project)
        await make_run(db, second, [["Coastline", "Aerials"]])
        second_id = second.id
        third = await make_asset(db, ws, project, status="partial")
        third_id = third.id
    base = f"/api/workspaces/{ws}/projects/{project}"
    summary = (await clients[0].get(base + "/organization")).json()
    assert summary["categories"] == [
        {"id": "coastline", "name": "Coastline", "asset_count": 2},
        {"id": "aerials", "name": "Aerials", "asset_count": 1},
        {"id": "waves", "name": "Waves", "asset_count": 1},
    ]
    assert summary["total_assets"] == 3 and summary["categorized_assets"] == 2
    assert summary["uncategorized_assets"] == summary["not_analyzed_assets"] == 1
    assert summary["analysis_configured"] is False
    assert summary["category_total"] == 3 and not summary["has_more"]
    pages = [
        (await clients[0].get(base + f"/assets?category=coastline&limit=1&offset={offset}")).json()
        for offset in (0, 1)
    ]
    assert all(page["total"] == 2 and len(page["items"]) == 1 for page in pages)
    assert {page["items"][0]["id"] for page in pages} == {str(asset_id), str(second_id)}
    assert all(page["items"][0]["organization"]["state"] == "organized" for page in pages)
    unassigned = (await clients[0].get(base + "/assets?category=uncategorized")).json()
    assert [item["id"] for item in unassigned["items"]] == [str(third_id)]
    # Collection membership remains an independent filter.
    assert (await clients[0].get(base + "/assets?uncollected=true")).json()["total"] == 3
    async with tenant_session(ws) as db:
        assert set(await category_asset_ids(db, ws, project, "coastline")) == {asset_id, second_id}
        assert await category_asset_ids(db, ws, project, "uncategorized") == [third_id]


@pytest.mark.integration
async def test_latest_run_only_completed_windows_and_legacy_states(authenticated):
    clients, ws, _, project, asset_id, _ = authenticated
    async with tenant_session(ws) as db:
        asset = await db.get(Asset, asset_id)
        await make_run(db, asset, [["Forest"]], created_at=datetime.now(UTC) - timedelta(days=1))
        latest, _ = await make_run(db, asset, [["Coastline"]], state="partial")
        latest_id = latest.id
        db.add(
            AnalysisWindow(
                workspace_id=ws,
                asset_id=asset.id,
                run_id=latest.id,
                start_us=0,
                end_us=1_000_000,
                cache_key=str(uuid.uuid4()),
                state="failed",
            )
        )
        processing = await make_asset(db, ws, project, status="processing")
        await make_run(
            db, processing, [["Hidden Pending Label"]], state="running", window_state="pending"
        )
        legacy = await make_asset(db, ws, project)
        await make_run(db, legacy, [["Legacy Must Not Appear"]], schema="observations-v1")
        no_categories = await make_asset(db, ws, project)
        await make_run(db, no_categories, [])
    base = f"/api/workspaces/{ws}/projects/{project}"
    summary = (await clients[0].get(base + "/organization")).json()
    assert summary["categories"] == [{"id": "coastline", "name": "Coastline", "asset_count": 1}]
    assert (
        summary["partial_assets"]
        == summary["processing_assets"]
        == summary["not_analyzed_assets"]
        == 1
    )
    detail = (await clients[0].get(f"/api/workspaces/{ws}/assets/{asset_id}")).json()
    assert detail["organization"]["state"] == "partial"
    assert detail["organization"]["run_id"] == str(latest_id)
    assert (await clients[0].get(base + "/assets?category=forest")).json()["total"] == 0


@pytest.mark.integration
@pytest.mark.parametrize("failed_state", ["failed", "canceled"])
async def test_resuming_current_run_reports_processing_and_keeps_completed_categories(
    authenticated, failed_state
):
    clients, ws, _, project, asset_id, _ = authenticated
    async with tenant_session(ws) as db:
        asset = await db.get(Asset, asset_id)
        run, _ = await make_run(db, asset, [["Coastline"]], state=failed_state)
        run_id = run.id
        db.add(
            AnalysisWindow(
                workspace_id=ws,
                asset_id=asset_id,
                run_id=run.id,
                start_us=0,
                end_us=1_000_000,
                cache_key=str(uuid.uuid4()),
                state="pending",
            )
        )
        db.add(
            Job(
                workspace_id=ws,
                project_id=project,
                asset_id=asset_id,
                kind="asset",
                state=failed_state,
                workflow_id=str(uuid.uuid4()),
            )
        )
    base = f"/api/workspaces/{ws}"
    summary_url = f"{base}/projects/{project}/organization"
    before = (await clients[0].get(summary_url)).json()
    assert before["partial_assets"] == 1 and before["processing_assets"] == 0
    response = await clients[0].post(f"{base}/assets/{asset_id}/retry")
    assert response.status_code == 202
    # The retry API and subsequent preparation stages must all override stale run status.
    for status in ("queued", "processing", "preview_ready"):
        async with tenant_session(ws) as db:
            asset = await db.get(Asset, asset_id)
            if status == "queued":
                assert asset.status == status
            else:
                asset.status = status
            assert (await db.get(AnalysisRun, run_id)).status == failed_state
        summary = (await clients[0].get(summary_url)).json()
        assert summary["processing_assets"] == 1 and summary["partial_assets"] == 0
        assert summary["categories"] == [{"id": "coastline", "name": "Coastline", "asset_count": 1}]
        detail = (await clients[0].get(f"{base}/assets/{asset_id}")).json()
        assert detail["organization"]["state"] == "processing"
        assert detail["organization"]["run_id"] == str(run_id)
        assert detail["organization"]["categories"] == [
            {"id": "coastline", "name": "Coastline", "evidence_count": 1}
        ]


@pytest.mark.integration
async def test_organization_member_read_cross_project_and_tenant_isolation(authenticated):
    clients, ws, other_ws, project, asset_id, _ = authenticated
    async with tenant_session(ws) as db:
        asset = await db.get(Asset, asset_id)
        await make_run(db, asset, [["Coastline"]])
        different_project = Project(workspace_id=ws, name="Other project")
        db.add(different_project)
        await db.flush()
        other_asset = await make_asset(db, ws, different_project.id)
        await make_run(db, other_asset, [["Separate Project"]])
    async with tenant_session(other_ws) as db:
        outsider_project = Project(workspace_id=other_ws, name="Private project")
        db.add(outsider_project)
        await db.flush()
        other_project_id = outsider_project.id
        outsider_asset = await make_asset(db, other_ws, outsider_project.id)
        await make_run(db, outsider_asset, [["Private Tenant"]])
    endpoint = f"/api/workspaces/{ws}/projects/{project}/organization"
    for client in clients[:2]:
        response = await client.get(endpoint)
        assert response.status_code == 200
        assert response.json()["categories"] == [
            {"id": "coastline", "name": "Coastline", "asset_count": 1}
        ]
    assert (await clients[2].get(endpoint)).status_code == 404
    assert (
        await clients[0].get(f"/api/workspaces/{ws}/projects/{other_project_id}/organization")
    ).status_code == 404
    invalid = await clients[0].get(
        f"/api/workspaces/{ws}/projects/{project}/assets", params={"category": "../private-tenant"}
    )
    assert invalid.status_code == 422
    async with tenant_session(ws) as db:
        assert await category_asset_ids(db, ws, project, "private-tenant") == []
        assert await category_asset_ids(db, ws, project, "separate-project") == []


@pytest.mark.integration
async def test_category_inventory_is_bounded_with_true_total(authenticated):
    clients, ws, _, project, asset_id, _ = authenticated
    async with tenant_session(ws) as db:
        await make_run(
            db,
            await db.get(Asset, asset_id),
            [[f"Scene {i + j}" for j in range(3)] for i in range(0, 102, 3)] + [["Scene 102"]],
        )
    result = (await clients[0].get(f"/api/workspaces/{ws}/projects/{project}/organization")).json()
    assert len(result["categories"]) == 100 and result["category_total"] == 103
    assert result["has_more"] is True and result["categorized_assets"] == 1
    detail = (await clients[0].get(f"/api/workspaces/{ws}/assets/{asset_id}")).json()
    assert len(detail["organization"]["categories"]) == 100
    assert detail["organization"]["category_total"] == 103
    assert detail["organization"]["has_more"] is True


@pytest.mark.integration
@pytest.mark.parametrize("legacy", [False, True])
async def test_received_categories_persist_idempotently_without_another_provider_call(
    authenticated, monkeypatch, legacy
):
    clients, ws, _, project, asset_id, _ = authenticated

    def no_provider(*args, **kwargs):
        raise AssertionError("Persisting a received response must not dispatch inference")

    monkeypatch.setattr(activities, "GeminiAnalyzer", no_provider)
    async with tenant_session(ws) as db:
        asset = await db.get(Asset, asset_id)
        run, window = await make_run(
            db,
            asset,
            [],
            window_state="received",
            schema="observations-v1" if legacy else SCHEMA_VERSION,
        )
        run_id, window_id = run.id, window.id
        window.raw_response = {
            "provider": {"synthetic": True},
            "envelope": {
                "text": json.dumps(
                    {
                        "observations": [
                            proposal() if legacy else proposal(["Coastline"]),
                            proposal() if legacy else proposal(["Waves"]),
                        ]
                    }
                ),
                "model": run.model,
            },
            "chunk_mapping": {"first_source_elapsed_us": 0},
        }
        db.add(
            Usage(
                workspace_id=ws,
                asset_id=asset_id,
                operation_key=f"analysis:{window_id}",
                kind="analysis",
                model=run.model,
            )
        )
    args = {"workspace_id": str(ws), "window_id": str(window_id)}
    assert await activities.apply_received_response(args) == "completed"
    assert await activities.apply_received_response(args) == "completed"
    async with tenant_session(ws) as db:
        observations = list(
            await db.scalars(select(Observation).where(Observation.run_id == run_id))
        )
        assert len(observations) == (1 if legacy else 2)
        assert (
            await db.scalar(
                select(func.count())
                .select_from(Usage)
                .where(Usage.operation_key == f"analysis:{window_id}")
            )
            == 1
        )
        if legacy:
            assert observations[0].attributes == {}
        else:
            assert {
                item["id"]
                for observation in observations
                for item in observation.attributes["categories"]
            } == {"coastline", "waves"}
    summary = (await clients[0].get(f"/api/workspaces/{ws}/projects/{project}/organization")).json()
    assert summary["category_total"] == (0 if legacy else 2)


@pytest.mark.integration
async def test_received_boundary_rounding_preserves_proposal_and_usage(authenticated, monkeypatch):
    _, ws, _, _, asset_id, _ = authenticated

    def no_provider(*args, **kwargs):
        raise AssertionError("Retained evidence must not dispatch inference")

    monkeypatch.setattr(activities, "GeminiAnalyzer", no_provider)
    async with tenant_session(ws) as db:
        asset = await db.get(Asset, asset_id)
        asset.duration_us = 14_006_667
        run, window = await make_run(db, asset, [], window_state="received")
        window.end_us = asset.duration_us
        run_id, window_id = run.id, window.id
        raw = {
            "provider": {"synthetic": True},
            "envelope": {
                "text": json.dumps(
                    {"observations": [{**proposal(["Coastline"]), "end_seconds": 14.007}]}
                ),
                "model": run.model,
            },
            "chunk_mapping": {"first_source_elapsed_us": 0},
        }
        window.raw_response = raw
        db.add(
            Usage(
                workspace_id=ws,
                asset_id=asset_id,
                operation_key=f"analysis:{window_id}",
                kind="analysis",
                model=run.model,
                input_tokens=123,
                output_tokens=45,
            )
        )
    args = {"workspace_id": str(ws), "window_id": str(window_id)}
    assert await activities.apply_received_response(args) == "completed"
    assert await activities.apply_received_response(args) == "completed"
    async with tenant_session(ws) as db:
        rows = list(await db.scalars(select(Observation).where(Observation.run_id == run_id)))
        assert len(rows) == 1
        assert rows[0].proposed_end_us == 14_007_000
        assert rows[0].end_us == 14_006_667
        assert (await db.get(AnalysisWindow, window_id)).raw_response == raw
        usages = list(
            await db.scalars(select(Usage).where(Usage.operation_key == f"analysis:{window_id}"))
        )
        assert len(usages) == 1
        assert (usages[0].input_tokens, usages[0].output_tokens, usages[0].provider_outcome) == (
            123,
            45,
            "confirmed",
        )
