import asyncio
import logging
import signal
from contextlib import asynccontextmanager
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
STARTUP_TIMEOUT_SECONDS = 30
SHUTDOWN_TIMEOUT_SECONDS = 35


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


async def stop_worker(worker, task):
    if task.done():
        return await task
    shutdown = asyncio.create_task(worker.shutdown())
    try:
        done, _ = await asyncio.wait({task, shutdown}, return_when=asyncio.FIRST_COMPLETED)
        if shutdown in done:
            await shutdown
        await task
    finally:
        shutdown.cancel()
        await asyncio.gather(shutdown, return_exceptions=True)


def consume_task_result(task):
    if not task.cancelled():
        task.exception()


async def require_workers_running(workers, tasks):
    async with asyncio.timeout(STARTUP_TIMEOUT_SECONDS):
        while True:
            for task in tasks:
                if task.done():
                    await task
                    raise RuntimeError("A RUSHES worker exited during startup")
            # The public property becomes true only after namespace validation succeeds.
            if all(worker.is_running for worker in workers):
                return
            await asyncio.wait(tasks, timeout=0.05, return_when=asyncio.FIRST_COMPLETED)


@asynccontextmanager
async def running_workers():
    config = settings()
    client = await asyncio.wait_for(
        Client.connect(config.temporal_address), STARTUP_TIMEOUT_SECONDS
    )
    fatal = asyncio.get_running_loop().create_future()

    async def on_fatal_error(error):
        if not fatal.done():
            fatal.set_exception(error)

    workers = [
        Worker(
            client,
            task_queue=MEDIA_QUEUE,
            workflows=list(WORKFLOWS.values()),
            activities=[*MEDIA_ACTIVITIES, render_export],
            max_concurrent_activities=2,
            max_concurrent_workflow_tasks=4,
            max_cached_workflows=8,
            graceful_shutdown_timeout=timedelta(seconds=30),
            on_fatal_error=on_fatal_error,
        ),
        Worker(
            client,
            task_queue=INFERENCE_QUEUE,
            activities=INFERENCE_ACTIVITIES,
            max_concurrent_activities=1,
            graceful_shutdown_timeout=timedelta(seconds=30),
            on_fatal_error=on_fatal_error,
        ),
    ]
    tasks = [asyncio.create_task(worker.run()) for worker in workers]
    background = []
    try:
        await require_workers_running(workers, [*tasks, fatal])
        background = [asyncio.create_task(dispatch(client)), asyncio.create_task(maintain())]
        yield [*tasks, *background, fatal]
    finally:
        for task in background:
            task.cancel()
        await asyncio.gather(*background, return_exceptions=True)
        draining = asyncio.gather(
            *(stop_worker(worker, task) for worker, task in zip(workers, tasks, strict=True)),
            return_exceptions=True,
        )
        try:
            done, _ = await asyncio.wait([draining], timeout=SHUTDOWN_TIMEOUT_SECONDS)
            if not done:
                raise TimeoutError("Worker shutdown exceeded its drain deadline")
            for outcome in draining.result():
                if isinstance(outcome, BaseException):
                    raise outcome
        finally:
            # Storage activities may drain through cancellation to keep their file leases.
            # Do not await them past this deadline; the process supervisor enforces the hard stop.
            for task in [draining, *tasks, fatal]:
                task.cancel()
                task.add_done_callback(consume_task_result)


async def main():
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stopping.set)
    async with running_workers() as tasks:
        stopped = asyncio.create_task(stopping.wait())
        try:
            done, _ = await asyncio.wait([stopped, *tasks], return_when=asyncio.FIRST_COMPLETED)
            if stopped not in done:
                await next(iter(done))
                raise RuntimeError("A RUSHES worker task exited unexpectedly")
        finally:
            stopped.cancel()
            await asyncio.gather(stopped, return_exceptions=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
