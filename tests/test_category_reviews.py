import asyncio
import copy
from pathlib import Path

import pytest
from rushes.config import settings
from rushes.db import tenant_session
from rushes.models import Asset, AssetCategoryReview, Export, Job, Observation
from rushes.storage import fingerprint
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from test_organization import make_run

pytestmark = pytest.mark.integration


async def reviewed_fixture(authenticated):
    clients, ws, other, project, asset_id, _ = authenticated
    async with tenant_session(ws) as db:
        asset = await db.get(Asset, asset_id)
        source = Path(asset.source_root) / asset.relative_path
        with source.open("rb") as file:
            asset.fingerprint = fingerprint(file)
        asset.source_size = source.stat().st_size
        await make_run(db, asset, [["Wrong"]])
        observation = await db.scalar(select(Observation).where(Observation.asset_id == asset_id))
        original = copy.deepcopy(observation.attributes)
    return clients, ws, other, project, asset_id, source, original


async def test_review_controls_counts_filters_exports_and_survives_reanalysis(
    authenticated, monkeypatch
):
    clients, ws, _, project, asset, source, original = await reviewed_fixture(authenticated)
    monkeypatch.setattr(settings(), "min_free_bytes", 0)
    client = clients[0]
    base = f"/api/workspaces/{ws}"
    project_base = f"{base}/projects/{project}"
    path = f"{base}/assets/{asset}"
    response = await client.put(
        path + "/categories", json={"version": 0, "categories": [" Coast ", "COAST"]}
    )
    assert response.status_code == 200, response.text
    review = response.json()
    assert review["categories"] == [{"id": "coast", "name": "Coast"}]
    summary = (await client.get(project_base + "/organization")).json()
    assert summary["categories"] == [{"id": "coast", "name": "Coast", "asset_count": 1}]
    assert (await client.get(project_base + "/assets?category=wrong")).json()["total"] == 0
    assert (await client.get(project_base + "/assets?category=coast")).json()["total"] == 1
    preview = await client.post(
        project_base + "/export-preview", json={"kind": "copies", "category": "coast"}
    )
    assert preview.status_code == 201, preview.text
    async with tenant_session(ws) as db:
        frozen = await db.get(Export, preview.json()["id"])
        evidence = frozen.plan["entries"][0]["organization"]["evidence"]
        assert evidence[0]["category_review_id"] == review["id"]
        assert evidence[0]["producer"] == "human" and "model" not in evidence[0]
        assert evidence[0]["user_id"] == review["user_id"]
        existing = await db.get(Asset, asset)
        await make_run(db, existing, [["Wrong Again"]])
        assert (
            await db.scalar(
                select(func.count()).select_from(Job).where(Job.kind.in_(["asset", "index"]))
            )
            == 0
        )
        assert (
            await db.scalar(select(Observation).where(Observation.attributes == original))
        ).attributes == original
    organization = (await client.get(path)).json()["organization"]
    assert [item["id"] for item in organization["categories"]] == ["coast"]
    assert organization["category_review"]["version"] == 1
    assert source.read_bytes() == b"0123456789"
    # Explicit empty review suppresses machine labels, including later runs.
    assert (
        await client.put(path + "/categories", json={"version": 1, "categories": []})
    ).status_code == 200
    assert (await client.get(project_base + "/assets?category=uncategorized")).json()["total"] == 1
    # Explicit reset restores the newest model labels without deleting reviews.
    assert (
        await client.put(path + "/categories", json={"version": 2, "categories": None})
    ).status_code == 200
    assert (await client.get(project_base + "/assets?category=wrong-again")).json()["total"] == 1
    history = (await client.get(path + "/category-history")).json()
    assert [r["version"] for r in history] == [3, 2, 1]
    assert history[0]["categories"] is None and history[1]["categories"] == []
    async with tenant_session(ws) as db:
        frozen = await db.get(Export, preview.json()["id"])
        assert frozen.plan["entries"][0]["organization"]["evidence"] == evidence


async def test_review_rejects_stale_concurrent_writes_and_invalid_labels(authenticated):
    clients, ws, _, _, asset, _, _ = await reviewed_fixture(authenticated)
    path = f"/api/workspaces/{ws}/assets/{asset}/categories"
    responses = await asyncio.gather(
        *[
            clients[0].put(path, json={"version": 0, "categories": [name]})
            for name in ("Coast", "Road")
        ]
    )
    assert sorted(r.status_code for r in responses) == [200, 409]
    saved = next(r.json() for r in responses if r.status_code == 200)
    repeated = await clients[0].put(
        path, json={"version": 1, "categories": [saved["categories"][0]["name"]]}
    )
    assert repeated.json()["version"] == 1
    for labels in (["../secret"], ["Uncategorized"], ["A" * 37], ["Coast"] * 101):
        assert (
            await clients[0].put(path, json={"version": 1, "categories": labels})
        ).status_code == 422


async def test_review_permissions_tenant_isolation_history_and_synthetic_deletion(authenticated):
    clients, ws, other, _, asset, _, _ = await reviewed_fixture(authenticated)
    path = f"/api/workspaces/{ws}/assets/{asset}"
    body = {"version": 0, "categories": ["Coast"]}
    assert (await clients[1].put(path + "/categories", json=body)).status_code == 403
    assert (
        await clients[2].put(f"/api/workspaces/{other}/assets/{asset}/categories", json=body)
    ).status_code == 404
    response = await clients[0].put(path + "/categories", json=body)
    assert response.status_code == 200
    history = await clients[1].get(path + "/category-history")
    assert history.status_code == 200 and len(history.json()) == 1
    async with tenant_session(other) as db:
        assert list(await db.scalars(select(AssetCategoryReview))) == []
    with pytest.raises(DBAPIError):
        async with tenant_session(ws) as db:
            await db.execute(text("UPDATE asset_category_review SET version=99"))
    with pytest.raises(DBAPIError):
        async with tenant_session(other) as db:
            db.add(
                AssetCategoryReview(
                    workspace_id=other,
                    asset_id=asset,
                    user_id=response.json()["user_id"],
                    version=2,
                    categories=[],
                )
            )
            await db.flush()
    assert (await clients[0].delete(path)).status_code == 200
    async with tenant_session(ws) as db:
        assert await db.scalar(select(func.count()).select_from(AssetCategoryReview)) == 0
