from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select

from rushes.api_common import DB, Access, owned, row_json
from rushes.auth import require_editor
from rushes.db import tenant_session
from rushes.models import Asset, Collection, CollectionItem, Project
from rushes.routes_search import retrieve
from rushes.timing import Interval

router = APIRouter(prefix="/api/workspaces/{workspace_id}")


class CollectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=160)
    instructions: str = Field(default="", max_length=2000)
    saved_query: str | None = Field(default=None, max_length=500)


class ItemAdjustment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_us: int | None = Field(default=None, ge=0)
    end_us: int | None = Field(default=None, gt=0)
    note: str = Field(default="", max_length=1000)

    def within(self, duration_us):
        if self.start_us is not None or self.end_us is not None:
            try:
                Interval(start_us=self.start_us, end_us=self.end_us).within(duration_us or 0)
            except ValueError as error:
                raise HTTPException(422, "Select valid in/out points within this source") from error


class ItemInput(ItemAdjustment):
    asset_id: UUID


@router.get("/projects/{project_id}/collections")
async def collections(project_id: UUID, db: DB, access: Access):
    await owned(db, Project, project_id, access)
    return [
        row_json(row)
        for row in await db.scalars(
            select(Collection)
            .where(Collection.project_id == project_id)
            .order_by(Collection.created_at)
            .limit(200)
        )
    ]


@router.post("/projects/{project_id}/collections", status_code=201)
async def create_collection(project_id: UUID, body: CollectionInput, db: DB, access: Access):
    require_editor(access)
    await owned(db, Project, project_id, access)
    await db.scalar(select(Project).where(Project.id == project_id).with_for_update())
    count = await db.scalar(
        select(func.count()).select_from(Collection).where(Collection.project_id == project_id)
    )
    if count >= 200:
        raise HTTPException(
            422,
            "Projects support up to 200 collections and saved searches. Remove one before creating another.",
        )
    collection = Collection(
        workspace_id=access.workspace_id, project_id=project_id, **body.model_dump()
    )
    db.add(collection)
    await db.flush()
    return row_json(collection)


@router.get("/collections/{collection_id}/items")
async def collection_items(collection_id: UUID, db: DB, access: Access):
    await owned(db, Collection, collection_id, access)
    rows = await db.execute(
        select(CollectionItem, Asset.name)
        .join(Asset, Asset.id == CollectionItem.asset_id)
        .where(CollectionItem.collection_id == collection_id)
        .order_by(CollectionItem.position, CollectionItem.created_at)
        .limit(500)
    )
    return [{**row_json(item), "asset_name": name} for item, name in rows]


@router.post("/collections/{collection_id}/items", status_code=201)
async def add_item(collection_id: UUID, body: ItemInput, db: DB, access: Access):
    require_editor(access)
    collection = await db.scalar(
        select(Collection).where(Collection.id == collection_id).with_for_update()
    )
    if collection is None:
        raise HTTPException(404, "Collection not found")
    count = await db.scalar(
        select(func.count())
        .select_from(CollectionItem)
        .where(CollectionItem.collection_id == collection_id)
    )
    if count >= 500:
        raise HTTPException(
            422, "Collections support up to 500 items. Create another collection to add more."
        )
    asset = await owned(db, Asset, body.asset_id, access)
    if asset.project_id != collection.project_id:
        raise HTTPException(422, "Select footage from this collection’s project")
    body.within(asset.duration_us)
    item = CollectionItem(
        workspace_id=access.workspace_id, collection_id=collection.id, **body.model_dump()
    )
    db.add(item)
    await db.flush()
    return row_json(item)


@router.delete("/collection-items/{item_id}", status_code=204)
async def remove_item(item_id: UUID, db: DB, access: Access):
    require_editor(access)
    item = await owned(db, CollectionItem, item_id, access)
    await db.delete(item)


@router.delete("/collections/{collection_id}", status_code=204)
async def remove_collection(collection_id: UUID, db: DB, access: Access):
    require_editor(access)
    collection = await owned(db, Collection, collection_id, access)
    await db.execute(delete(CollectionItem).where(CollectionItem.collection_id == collection.id))
    await db.delete(collection)


class SuggestInput(BaseModel):
    instructions: str = Field(min_length=1, max_length=500)


@router.post("/collections/{collection_id}/suggest")
async def suggest(collection_id: UUID, body: SuggestInput, access: Access):
    require_editor(access)
    async with tenant_session(access.workspace_id) as db:
        collection = await owned(db, Collection, collection_id, access)
        project_id = collection.project_id
    results, error, incomplete = await retrieve(access, project_id, body.instructions)
    return {
        "suggestions": [
            {
                "asset_id": result["asset_id"],
                "asset_name": result["asset_name"],
                "start_us": result["start_us"],
                "end_us": result["end_us"],
                "evidence": result["evidence"],
            }
            for result in results
        ],
        "notice": error,
        "incomplete_processing": incomplete,
        "instructions": "Review suggested ranges before adding them. Suggestions do not move files.",
    }


@router.patch("/collection-items/{item_id}")
async def adjust_item(item_id: UUID, body: ItemAdjustment, db: DB, access: Access):
    require_editor(access)
    item = await db.scalar(
        select(CollectionItem).where(CollectionItem.id == item_id).with_for_update()
    )
    if item is None:
        raise HTTPException(404, "Record not found")
    asset = await owned(db, Asset, item.asset_id, access)
    changes = body.model_dump(exclude_unset=True)
    merged = ItemAdjustment(
        **{**{key: getattr(item, key) for key in ItemAdjustment.model_fields}, **changes}
    )
    merged.within(asset.duration_us)
    for key, value in changes.items():
        setattr(item, key, value)
    return row_json(item)
