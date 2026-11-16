from uuid import UUID

from fastapi import APIRouter, Query

from rushes.api_common import DB, Access, owned
from rushes.config import settings
from rushes.models import Project
from rushes.organization import CATEGORY_SLUG_PATTERN, project_categories, project_organization

router = APIRouter(prefix="/api/workspaces/{workspace_id}")


@router.get("/projects/{project_id}/categories")
async def categories(
    project_id: UUID,
    db: DB,
    access: Access,
    after: str | None = Query(None, min_length=1, max_length=36, pattern=CATEGORY_SLUG_PATTERN),
    limit: int = Query(50, ge=1, le=100),
):
    await owned(db, Project, project_id, access)
    return await project_categories(db, access.workspace_id, project_id, after=after, limit=limit)


@router.get("/projects/{project_id}/organization")
async def organization(project_id: UUID, db: DB, access: Access):
    await owned(db, Project, project_id, access)
    result = await project_organization(db, access.workspace_id, project_id)
    key = settings().gemini_api_key
    return {**result, "analysis_configured": bool(key and key.get_secret_value())}
