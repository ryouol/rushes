import asyncio
import logging
import signal
from datetime import timedelta

from sqlalchemy import or_, select
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode
from temporalio.worker import Worker

from rushes.activities import INFERENCE_ACTIVITIES, MEDIA_ACTIVITIES, finalize_failure
from rushes.config import settings
from rushes.db import session_factory, tenant_session
from rushes.exports import render_export
from rushes.maintenance import maintain
from rushes.models import Job, Workspace
from rushes.workflows import (
    INFERENCE_QUEUE,
    MEDIA_QUEUE,
    AssetWorkflow,
    BatchWorkflow,
    ExportWorkflow,
    IndexWorkflow,
)

logger = logging.getLogger("rushes.worker")
WORKFLOWS = {
    "asset": AssetWorkflow,
    "batch": BatchWorkflow,
    "export": ExportWorkflow,
    "index": IndexWorkflow,
}


async def dispatch_workspace(client, workspace_id):
    async with tenant_session(workspace_id) as db:
        ids = list(
            await db.scalars(
                select(Job.id)
                .where(
                    Job.state.in_(["queued", "cancel_requested"]),
                    or_(
                        Job.state == "cancel_requested",
                        Job.payload["batch_id"].astext.is_(None),
                    ),
                )
                .order_by(Job.created_at)
                .limit(40)
            )
        )
    for id in ids:
        # Serialize dispatch with user cancellation. The stable workflow ID also closes the crash-after-start gap.
        async with tenant_session(workspace_id) as db:
            job = await db.scalar(select(Job).where(Job.id == id).with_for_update(skip_locked=True))
            if job is None or job.kind not in WORKFLOWS:
                continue
            if job.state == "cancel_requested":
                try:
                    await asyncio.wait_for(
                        client.get_workflow_handle(job.workflow_id).cancel(), timeout=5
                    )
                except RPCError as error:
                    if error.status != RPCStatusCode.NOT_FOUND:
                        raise
                    await finalize_failure(
                        db,
                        {
                            "workspace_id": str(workspace_id),
                            "job_id": str(job.id),
                            "state": "canceled",
                            "error": "Canceled; no active workflow exists for this job.",
                        },
                    )
                continue
            if job.state != "queued" or job.payload.get("batch_id"):
                continue
            args = {
                "workspace_id": str(workspace_id),
                "job_id": str(job.id),
                "asset_id": str(job.asset_id),
                "project_id": str(job.project_id),
            }
            try:
                await asyncio.wait_for(
                    client.start_workflow(
                        WORKFLOWS[job.kind].run,
                        args,
                        id=job.workflow_id,
                        task_queue=MEDIA_QUEUE,
                    ),
                    timeout=5,
                )
            except WorkflowAlreadyStartedError:
                pass
            job.state, job.stage = "dispatched", "Waiting for worker"


async def dispatch(client: Client):
    while True:
        try:
            async with session_factory()() as db:
                workspace_ids = list(await db.scalars(select(Workspace.id)))
            for workspace_id in workspace_ids:
                try:
                    await dispatch_workspace(client, workspace_id)
                except Exception:
                    logger.exception("Workspace dispatch interrupted; its queued work will retry")
        except Exception:
            logger.exception("Job dispatch interrupted; durable queued work will be retried")
        await asyncio.sleep(3)


async def main():
    config = settings()
    client = await Client.connect(config.temporal_address)
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stopping.set)
    async with (
        Worker(
            client,
            task_queue=MEDIA_QUEUE,
            workflows=list(WORKFLOWS.values()),
            activities=[*MEDIA_ACTIVITIES, render_export],
            max_concurrent_activities=2,
            graceful_shutdown_timeout=timedelta(seconds=30),
        ) as media_worker,
        Worker(
            client,
            task_queue=INFERENCE_QUEUE,
            activities=INFERENCE_ACTIVITIES,
            max_concurrent_activities=1,
            graceful_shutdown_timeout=timedelta(seconds=30),
        ) as inference_worker,
    ):
        dispatcher = asyncio.create_task(dispatch(client))
        maintenance = asyncio.create_task(maintain())
        try:
            await stopping.wait()
        finally:
            dispatcher.cancel()
            maintenance.cancel()
            await asyncio.gather(dispatcher, maintenance, return_exceptions=True)
            await asyncio.gather(media_worker.shutdown(), inference_worker.shutdown())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
