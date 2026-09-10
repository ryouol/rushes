import asyncio
from uuid import UUID

from fastapi import APIRouter, Query
from pgvector.sqlalchemy import Vector
from sqlalchemy import cast, func, literal, select, text

from rushes.api_common import DB, Access, owned, row_json
from rushes.config import settings
from rushes.db import tenant_session
from rushes.inference import embedder
from rushes.models import Asset, Embedding, Observation, Project
from rushes.provider_budget import ProviderBudgetError

router = APIRouter(prefix="/api/workspaces/{workspace_id}")
search_limit = asyncio.Semaphore(1)


async def search_evidence(
    db, access, project_id: UUID, query: str, limit: int, vector, semantic_error
):
    keywords = await db.execute(
        text("""SELECT o.id FROM observation o JOIN asset a ON a.id=o.asset_id
        WHERE o.workspace_id=:workspace AND a.project_id=:project
        AND to_tsvector('english', o.description) @@ websearch_to_tsquery('english', :query)
        ORDER BY ts_rank_cd(to_tsvector('english', o.description), websearch_to_tsquery('english', :query)) DESC
        LIMIT 60"""),
        {"workspace": access.workspace_id, "project": project_id, "query": query},
    )
    keyword_ids = list(keywords.scalars())
    vector_ids = []
    if vector is not None:
        try:
            async with db.begin_nested():
                await db.execute(text("SET LOCAL hnsw.iterative_scan = 'strict_order'"))
                await db.execute(text("SET LOCAL hnsw.max_scan_tuples = 10000"))
                distance = cast(Embedding.vector, Vector(len(vector))).cosine_distance(vector)
                vector_ids = list(
                    await db.scalars(
                        select(Observation.id)
                        .join(Embedding, Embedding.observation_id == Observation.id)
                        .join(Asset, Asset.id == Observation.asset_id)
                        .where(
                            Observation.workspace_id == access.workspace_id,
                            Embedding.workspace_id == access.workspace_id,
                            Asset.project_id == project_id,
                            Embedding.model
                            == literal(settings().embedding_model, literal_execute=True),
                            Embedding.dimension == len(vector),
                            distance < 0.65,
                        )
                        .order_by(distance)
                        .limit(60)
                    )
                )
        except Exception:
            semantic_error = "Semantic index unavailable; keyword evidence is shown. Rebuild the configured model index."
    scores = {}
    for ranking in [keyword_ids, vector_ids]:
        for rank, id in enumerate(ranking, 1):
            scores[id] = scores.get(id, 0) + 1 / (60 + rank)
    if not scores:
        return [], semantic_error
    ids = sorted(scores, key=scores.get, reverse=True)[:60]
    matches = {
        row.id: row
        for row in await db.scalars(
            select(Observation).where(
                Observation.id.in_(ids), Observation.workspace_id == access.workspace_id
            )
        )
    }
    assets = {
        row.id: row
        for row in await db.scalars(
            select(Asset).where(Asset.id.in_([row.asset_id for row in matches.values()]))
        )
    }
    results = []
    for id in ids:
        observation = matches.get(id)
        if observation is None:
            continue
        overlap = next(
            (
                result
                for result in results
                if result["asset_id"] == observation.asset_id
                and result["start_us"] <= observation.end_us + 500_000
                and result["end_us"] >= observation.start_us - 500_000
            ),
            None,
        )
        evidence = {
            "observation_id": observation.id,
            "description": observation.description,
            "start_us": observation.start_us,
            "end_us": observation.end_us,
            "kind": observation.kind,
            "review_status": observation.review_status,
        }
        if overlap:
            overlap["start_us"] = min(overlap["start_us"], observation.start_us)
            overlap["end_us"] = max(overlap["end_us"], observation.end_us)
            overlap["evidence"].append(evidence)
        elif len(results) < limit:
            asset = assets[observation.asset_id]
            results.append(
                {
                    "asset_id": asset.id,
                    "asset_name": asset.name,
                    "start_us": observation.start_us,
                    "end_us": observation.end_us,
                    "score": scores[id],
                    "evidence": [evidence],
                    "processing_status": asset.status,
                    "has_thumbnail": bool(asset.thumbnail_path),
                }
            )
    return results, semantic_error


async def query_embedding(query):
    try:
        await asyncio.wait_for(search_limit.acquire(), timeout=0.05)
    except TimeoutError:
        return None, "Semantic search is busy; keyword evidence is shown. Try again shortly."
    task = asyncio.create_task(asyncio.to_thread(lambda: embedder().embed([query])[0]))

    def finished(task):
        search_limit.release()
        if not task.cancelled():
            task.exception()

    task.add_done_callback(finished)
    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout=3), None
    except ProviderBudgetError as error:
        return None, f"{error} Keyword evidence is shown."
    except Exception:
        return (
            None,
            "Semantic search is warming up or unavailable; keyword evidence is shown. Try again shortly.",
        )


async def retrieve(access, project_id, query, limit=20):
    async with tenant_session(access.workspace_id) as db:
        await owned(db, Project, project_id, access)
    vector, notice = await query_embedding(query)
    async with tenant_session(access.workspace_id) as db:
        results, notice = await search_evidence(
            db, access, project_id, query, limit, vector, notice
        )
        incomplete = await db.scalar(
            select(Asset.id).where(Asset.project_id == project_id, Asset.status != "ready").limit(1)
        )
    return results, notice, bool(incomplete)


@router.get("/projects/{project_id}/search")
async def search(
    project_id: UUID,
    access: Access,
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(20, ge=1, le=40),
):
    results, error, incomplete = await retrieve(access, project_id, q, limit)
    return {
        "results": results,
        "mode": "keyword" if error else "hybrid",
        "notice": error,
        "incomplete_processing": bool(incomplete),
        "evidence_status": "matches_found" if results else "insufficient_evidence",
    }


@router.get("/observations/{observation_id}/context")
async def context(observation_id: UUID, db: DB, access: Access):
    observation = await owned(db, Observation, observation_id, access)
    neighbors = await db.scalars(
        select(Observation)
        .where(
            Observation.asset_id == observation.asset_id,
            Observation.id != observation.id,
            Observation.start_us < observation.end_us + 5_000_000,
            Observation.end_us > max(0, observation.start_us - 5_000_000),
        )
        .order_by(func.abs(Observation.start_us - observation.start_us), Observation.id)
        .limit(11)
    )
    return {
        "citation": {
            "observation_id": observation.id,
            "asset_id": observation.asset_id,
            "start_us": observation.start_us,
            "end_us": observation.end_us,
        },
        "evidence": [row_json(observation), *[row_json(row) for row in neighbors]],
    }
