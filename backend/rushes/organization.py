"""Evidence-backed whole-file organization, without another inference request."""

import re
from uuid import UUID

from sqlalchemy import case, cast, exists, func, literal, select, true, type_coerce
from sqlalchemy.dialects.postgresql import JSONB

from rushes.models import AnalysisRun, AnalysisWindow, Asset, Observation

ORGANIZATION_VERSION = "categories-v1"
ORGANIZATION_SCHEMA_VERSION = "observations-v2"
CATEGORY_SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
ACTIVE_ASSET_STATES = ("queued", "processing", "preview_ready")


def category_label(value: str) -> str:
    """Normalize only spelling/case; semantic grouping belongs to the model."""
    if not isinstance(value, str) or not 1 <= len(value) <= 36:
        raise ValueError("Category names must contain 1 to 36 characters")
    name = " ".join(value.split())
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9 &'\-]*", name) or len(name.split()) > 6:
        raise ValueError("Use a short English category name without markup or path characters")
    if category_slug(name) == "uncategorized":
        raise ValueError("Uncategorized is reserved for files without an AI category")
    return name.title()


def category_slug(name: str) -> str:
    return "-".join(re.findall(r"[a-z0-9]+", name.lower()))


def category_records(names: list[str]) -> list[dict]:
    categories = {}
    for value in names:
        name = category_label(value)
        key = category_slug(name)
        categories[key] = {"id": key, "name": name}
    return [categories[key] for key in sorted(categories)]


def latest_organization_runs(workspace_id: UUID, project_id: UUID):
    ranked = (
        select(
            AnalysisRun.id.label("run_id"),
            AnalysisRun.asset_id,
            AnalysisRun.status,
            func.row_number()
            .over(
                partition_by=AnalysisRun.asset_id,
                order_by=(AnalysisRun.created_at.desc(), AnalysisRun.id.desc()),
            )
            .label("rank"),
        )
        .join(Asset, Asset.id == AnalysisRun.asset_id)
        .where(
            Asset.workspace_id == workspace_id,
            Asset.project_id == project_id,
            AnalysisRun.workspace_id == workspace_id,
            AnalysisRun.schema_version == ORGANIZATION_SCHEMA_VERSION,
        )
        .subquery()
    )
    return select(ranked).where(ranked.c.rank == 1).cte("organization_runs")


def organization_memberships(workspace_id: UUID, project_id: UUID, runs=None):
    """One row per category/asset/evidence, scoped before any API aggregation."""
    runs = runs if runs is not None else latest_organization_runs(workspace_id, project_id)
    category_array = case(
        (
            func.jsonb_typeof(Observation.attributes["categories"]) == "array",
            Observation.attributes["categories"],
        ),
        else_=cast(literal("[]"), JSONB),
    )
    values = (
        func.jsonb_array_elements(category_array).table_valued("value").lateral("category_values")
    )
    value = type_coerce(values.c.value, JSONB)
    return (
        select(
            Observation.asset_id,
            Observation.id.label("observation_id"),
            value["id"].as_string().label("category_id"),
            value["name"].as_string().label("category_name"),
        )
        .join(runs, runs.c.run_id == Observation.run_id)
        .join(AnalysisWindow, AnalysisWindow.id == Observation.window_id)
        .join(values, true())
        .where(
            Observation.workspace_id == workspace_id,
            Observation.asset_id == runs.c.asset_id,
            Observation.attributes["organization_version"].as_string() == ORGANIZATION_VERSION,
            AnalysisWindow.workspace_id == workspace_id,
            AnalysisWindow.run_id == runs.c.run_id,
            AnalysisWindow.asset_id == Observation.asset_id,
            AnalysisWindow.state == "completed",
            value["id"].as_string().op("~")(CATEGORY_SLUG_PATTERN),
            func.length(value["id"].as_string()) <= 36,
            value["id"].as_string() != "uncategorized",
        )
        .cte("organization_memberships")
    )


def category_asset_query(workspace_id: UUID, project_id: UUID, category: str):
    """Reusable DISTINCT source IDs; callers authorize the project before executing."""
    memberships = organization_memberships(workspace_id, project_id)
    query = select(Asset.id).where(
        Asset.workspace_id == workspace_id, Asset.project_id == project_id
    )
    matching = select(memberships.c.asset_id).where(memberships.c.asset_id == Asset.id)
    if category == "uncategorized":
        return query.where(~exists(matching))
    return query.where(exists(matching.where(memberships.c.category_id == category)))


async def category_asset_ids(db, workspace_id, project_id, category, limit=501):
    return list(
        await db.scalars(
            category_asset_query(workspace_id, project_id, category).order_by(Asset.id).limit(limit)
        )
    )


def organization_states(workspace_id: UUID, project_id: UUID, runs=None):
    runs = runs if runs is not None else latest_organization_runs(workspace_id, project_id)
    coverage = (
        select(
            AnalysisWindow.run_id,
            func.count().label("windows"),
            func.count().filter(AnalysisWindow.state == "completed").label("completed"),
        )
        .join(runs, runs.c.run_id == AnalysisWindow.run_id)
        .where(
            AnalysisWindow.workspace_id == workspace_id,
            AnalysisWindow.asset_id == runs.c.asset_id,
        )
        .group_by(AnalysisWindow.run_id)
        .cte("organization_coverage")
    )
    state = case(
        # Resuming an asset job preserves its run/checkpoints, including the old run status.
        (Asset.status.in_(ACTIVE_ASSET_STATES), "processing"),
        (runs.c.run_id.is_(None), "not_analyzed"),
        (
            (coverage.c.windows > 0) & (coverage.c.completed == coverage.c.windows),
            "organized",
        ),
        (runs.c.status.in_(("queued", "running")), "processing"),
        else_="partial",
    )
    return (
        select(Asset.id.label("asset_id"), runs.c.run_id, state.label("state"))
        .outerjoin(runs, runs.c.asset_id == Asset.id)
        .outerjoin(coverage, coverage.c.run_id == runs.c.run_id)
        .where(Asset.workspace_id == workspace_id, Asset.project_id == project_id)
        .cte("organization_states")
    )


async def asset_organizations(db, workspace_id, project_id, asset_ids):
    if not asset_ids:
        return {}
    states = organization_states(workspace_id, project_id)
    result = {
        row.asset_id: {
            "state": row.state,
            "run_id": row.run_id,
            "categories": [],
            "category_total": 0,
            "has_more": False,
        }
        for row in await db.execute(select(states).where(states.c.asset_id.in_(asset_ids)))
    }
    memberships = organization_memberships(workspace_id, project_id)
    counts = (
        select(
            memberships.c.asset_id,
            memberships.c.category_id,
            func.min(memberships.c.category_name).label("name"),
            func.count(func.distinct(memberships.c.observation_id)).label("evidence_count"),
        )
        .where(memberships.c.asset_id.in_(asset_ids))
        .group_by(memberships.c.asset_id, memberships.c.category_id)
        .subquery()
    )
    ranked = select(
        counts,
        func.row_number()
        .over(
            partition_by=counts.c.asset_id,
            order_by=(counts.c.evidence_count.desc(), counts.c.category_id),
        )
        .label("rank"),
        func.count().over(partition_by=counts.c.asset_id).label("category_total"),
    ).subquery()
    categories = await db.execute(
        select(ranked).where(ranked.c.rank <= 100).order_by(ranked.c.asset_id, ranked.c.rank)
    )
    for row in categories:
        result[row.asset_id]["category_total"] = row.category_total
        result[row.asset_id]["has_more"] = row.category_total > 100
        result[row.asset_id]["categories"].append(
            {"id": row.category_id, "name": row.name, "evidence_count": row.evidence_count}
        )
    return result


async def project_organization(db, workspace_id, project_id):
    memberships = organization_memberships(workspace_id, project_id)
    counts = (
        select(
            memberships.c.category_id.label("id"),
            func.min(memberships.c.category_name).label("name"),
            func.count(func.distinct(memberships.c.asset_id)).label("asset_count"),
        )
        .group_by(memberships.c.category_id)
        .subquery()
    )
    categories = (
        await db.execute(
            select(counts, func.count().over().label("category_total"))
            .order_by(counts.c.asset_count.desc(), counts.c.name, counts.c.id)
            .limit(100)
        )
    ).all()
    category_total = categories[0].category_total if categories else 0
    categorized = await db.scalar(select(func.count(func.distinct(memberships.c.asset_id))))
    states = organization_states(workspace_id, project_id)
    state_counts = dict(
        (await db.execute(select(states.c.state, func.count()).group_by(states.c.state))).all()
    )
    total = sum(state_counts.values())
    return {
        "categories": [
            {"id": row.id, "name": row.name, "asset_count": row.asset_count}
            for row in categories
        ],
        "category_total": category_total,
        "has_more": category_total > 100,
        "total_assets": total,
        "categorized_assets": categorized,
        "uncategorized_assets": total - categorized,
        "processing_assets": state_counts.get("processing", 0),
        "partial_assets": state_counts.get("partial", 0),
        "not_analyzed_assets": state_counts.get("not_analyzed", 0),
    }
