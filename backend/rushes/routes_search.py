from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pgvector.sqlalchemy import Vector
from sqlalchemy import cast, func, literal, literal_column, select, text

from rushes.api_common import DB, Access, owned, row_json
from rushes.config import settings
from rushes.db import tenant_session
from rushes.evidence import current_observation
from rushes.inference import embedder
from rushes.models import Asset, Embedding, Observation, Project
from rushes.provider_budget import ProviderBudgetError
from rushes.search_compute import cache_key, computations, relevance_scores
from rushes.telemetry import traced

router = APIRouter(prefix="/api/workspaces/{workspace_id}")


@traced("search_evidence")
async def search_evidence(
    db, access, project_id: UUID, query: str, limit: int, vector, semantic_error
):
    document = func.to_tsvector(literal_column("'english'"), Observation.description)
    phrase = func.websearch_to_tsquery(literal_column("'english'"), query)
    keywords = await db.execute(
        select(Observation.id)
        .join(Asset, Asset.id == Observation.asset_id)
        .where(
            Observation.workspace_id == access.workspace_id,
            Asset.project_id == project_id,
            current_observation(),
            document.op("@@")(phrase),
        )
        .order_by(func.ts_rank_cd(document, phrase).desc())
        .limit(60)
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
                            current_observation(),
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
                Observation.id.in_(ids),
                Observation.workspace_id == access.workspace_id,
                current_observation(),
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
        evidence = {
            "observation_id": observation.id,
            "description": observation.description,
            "start_us": observation.start_us,
            "end_us": observation.end_us,
            "kind": observation.kind,
            "review_status": observation.review_status,
        }
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
        if len(results) >= limit:
            break
    return results, semantic_error


@traced("query_embedding")
async def query_embedding(query, workspace=""):
    # The BGE model card recommends this instruction for query-to-passage retrieval.
    text = (
        "Represent this sentence for searching relevant passages: " + query
        if settings().embedding_model == "BAAI/bge-small-en-v1.5"
        else query
    )
    try:
        vector = await computations.get(
            cache_key("query", workspace, query), lambda: embedder().embed([text])[0]
        )
        return vector, None
    except ProviderBudgetError as error:
        return None, f"{error} Keyword evidence is shown."
    except Exception:
        return (
            None,
            "Semantic search is starting or unavailable. Keyword evidence is shown; retrying this query reuses any completed search work.",
        )


def distinct_moments(results, limit):
    selected = []
    for result in results:
        duplicate = next(
            (
                row
                for row in selected
                if (
                    row["asset_id"] == result["asset_id"]
                    and row["start_us"] == result["start_us"]
                    and row["end_us"] == result["end_us"]
                )
            ),
            None,
        )
        if duplicate:
            duplicate["evidence"].extend(result["evidence"])
        elif len(selected) < limit:
            selected.append(result)
    return selected


@traced("retrieve")
async def retrieve(access, project_id, query, limit=20, semantic=True):
    async with tenant_session(access.workspace_id) as db:
        await owned(db, Project, project_id, access)
    query = " ".join(query.split())
    if not query:
        raise HTTPException(422, "Enter a search phrase")
    vector, notice = (
        await query_embedding(query, access.workspace_id)
        if semantic
        else (None, "Text matches are shown while semantic search checks the footage.")
    )
    async with tenant_session(access.workspace_id) as db:
        results, notice = await search_evidence(db, access, project_id, query, 60, vector, notice)
        incomplete = await db.scalar(
            select(Asset.id).where(Asset.project_id == project_id, Asset.status != "ready").limit(1)
        )
    if results and not notice:
        try:
            scores = await relevance_scores(
                access.workspace_id,
                query,
                [result["evidence"][0]["description"] for result in results],
            )
            ranked = []
            for result, score in zip(results, scores, strict=True):
                if score >= -3:
                    ranked.append({**result, "score": score})
            results = sorted(ranked, key=lambda result: result["score"], reverse=True)
        except Exception as error:
            notice = (
                f"{error} Keyword evidence is shown."
                if isinstance(error, ProviderBudgetError)
                else "Relevance checking is starting or unavailable. Keyword evidence is shown; try again shortly."
            )
            async with tenant_session(access.workspace_id) as db:
                results, _ = await search_evidence(db, access, project_id, query, 60, None, notice)
    return distinct_moments(results, limit), notice, bool(incomplete)


@router.get("/projects/{project_id}/search")
async def search(
    project_id: UUID,
    access: Access,
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(20, ge=1, le=40),
    semantic: bool = True,
):
    results, error, incomplete = await retrieve(access, project_id, q, limit, semantic)
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
    superseded = not await db.scalar(
        select(current_observation()).where(Observation.id == observation.id)
    )
    neighbors = await db.scalars(
        select(Observation)
        .where(
            Observation.asset_id == observation.asset_id,
            Observation.id != observation.id,
            current_observation(),
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
            "superseded": superseded,
        },
        "evidence": [
            {**row_json(observation), "superseded": superseded},
            *[{**row_json(row), "superseded": False} for row in neighbors],
        ],
    }
