import uuid
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rushes.auth import WorkspaceAccess, workspace_access, workspace_db

DB = Annotated[AsyncSession, Depends(workspace_db)]
Access = Annotated[WorkspaceAccess, Depends(workspace_access)]


def row_json(row):
    return {column.key: getattr(row, column.key) for column in row.__table__.columns}


async def owned(db: AsyncSession, model, id: uuid.UUID, access: WorkspaceAccess):
    record = await db.scalar(
        select(model).where(model.id == id, model.workspace_id == access.workspace_id)
    )
    if record is None:
        raise HTTPException(404, "Record not found")
    return record
