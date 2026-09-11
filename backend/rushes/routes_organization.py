from uuid import UUID

from fastapi import APIRouter

from rushes.api_common import DB, Access, owned
from rushes.config import settings
from rushes.models import Project
from rushes.organization import project_organization

router = APIRouter(prefix="/api/workspaces/{workspace_id}")


@router.get("/projects/{project_id}/organization")
async def organization(project_id: UUID, db: DB, access: Access):
    await owned(db, Project, project_id, access)
    result = await project_organization(db, access.workspace_id, project_id)
    key = settings().gemini_api_key
    return {**result, "analysis_configured": bool(key and key.get_secret_value())}
