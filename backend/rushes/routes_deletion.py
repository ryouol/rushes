from uuid import UUID

from fastapi import APIRouter

from rushes.api_common import Access
from rushes.deletion import delete_resource

router = APIRouter(prefix="/api/workspaces/{workspace_id}")


@router.delete("")
async def delete_workspace(access: Access):
    return await delete_resource(access, "workspace", access.workspace_id)


@router.delete("/projects/{project_id}")
async def delete_project(project_id: UUID, access: Access):
    return await delete_resource(access, "project", project_id)


@router.delete("/assets/{asset_id}")
async def delete_asset(asset_id: UUID, access: Access):
    return await delete_resource(access, "asset", asset_id)


@router.delete("/exports/{export_id}")
async def delete_export(export_id: UUID, access: Access):
    return await delete_resource(access, "export", export_id)
