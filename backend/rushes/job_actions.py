import uuid

from sqlalchemy import select

from rushes.models import Asset, Job


def queue_asset(db, asset, *, kind="asset", payload=None):
    job_id = uuid.uuid4()
    job = Job(
        id=job_id,
        workspace_id=asset.workspace_id,
        project_id=asset.project_id,
        asset_id=asset.id,
        kind=kind,
        payload=payload or {},
        workflow_id=f"{kind}:{asset.id}:{job_id}",
    )
    db.add(job)
    return job


async def cancel_batch_children(db, batch_id):
    children = await db.scalars(
        select(Job)
        .where(
            Job.payload["batch_id"].astext == str(batch_id),
            Job.state.in_(["queued", "dispatched", "running"]),
        )
        .with_for_update()
    )
    for child in children:
        if child.state == "queued":
            child.state = "canceled"
            asset = await db.get(Asset, child.asset_id)
            asset.status, asset.error = "canceled", "Batch canceled before processing"
        else:
            child.state = "cancel_requested"
