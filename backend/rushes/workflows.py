import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

MEDIA_QUEUE = "rushes-media"
INFERENCE_QUEUE = "rushes-inference"
RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2,
    maximum_interval=timedelta(seconds=60),
    maximum_attempts=3,
    non_retryable_error_types=["ValueError", "StorageError", "CreditError", "ProviderBudgetError"],
)


async def media_activity(name: str, args: dict):
    return await workflow.execute_activity(
        name,
        args,
        task_queue=MEDIA_QUEUE,
        start_to_close_timeout=timedelta(hours=8),
        heartbeat_timeout=timedelta(minutes=2),
        retry_policy=RETRY,
        cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
    )


def failure_message(error: Exception) -> str:
    current = error
    for _ in range(8):
        if isinstance(current, ApplicationError) and current.type in {
            "MediaError",
            "StorageError",
            "CreditError",
            "ValueError",
            "ProviderBudgetError",
        }:
            return current.message[:1000]
        cause = getattr(current, "cause", None)
        if not isinstance(cause, Exception) or cause is current:
            break
        current = cause
    return str(error)[:1000]


async def report_failure(args: dict, state: str, error: str | Exception):
    message = error if isinstance(error, str) else failure_message(error)
    return await workflow.execute_activity(
        "fail_job",
        {**args, "state": state, "error": message},
        task_queue=MEDIA_QUEUE,
        start_to_close_timeout=timedelta(minutes=2),
        retry_policy=RETRY,
    )


@workflow.defn
class AssetWorkflow:
    @workflow.run
    async def run(self, args: dict):
        try:
            if not args.get("prepared"):
                await media_activity("prepare", args)
                args["prepared"] = True
            if not args.get("transcribed"):
                await media_activity("transcribe", args)
                args["transcribed"] = True
            if not args.get("planned"):
                plan = await media_activity("plan_analysis", args)
                args.update(plan)
                args["planned"] = True
            if args.get("run_id"):
                while True:
                    next_window = await media_activity("next_window", args)
                    if not next_window:
                        break
                    await media_activity("prepare_window", {**args, "window_id": next_window})
                    await workflow.execute_activity(
                        "analyze_window",
                        {**args, "window_id": next_window},
                        task_queue=INFERENCE_QUEUE,
                        start_to_close_timeout=timedelta(minutes=8),
                        heartbeat_timeout=timedelta(minutes=2),
                        retry_policy=RETRY,
                    )
                    info = workflow.info()
                    if (
                        info.is_continue_as_new_suggested()
                        or info.get_current_history_length() > 1000
                    ):
                        workflow.continue_as_new(args)
            await workflow.execute_activity(
                "embed_asset",
                args,
                task_queue=INFERENCE_QUEUE,
                start_to_close_timeout=timedelta(minutes=30),
                heartbeat_timeout=timedelta(minutes=2),
                retry_policy=RETRY,
            )
            return await media_activity("finish_asset", args)
        except asyncio.CancelledError:
            await report_failure(args, "canceled", "Canceled by user")
            raise
        except Exception as error:
            await report_failure(args, "failed", error)
            raise


@workflow.defn
class BatchWorkflow:
    @workflow.run
    async def run(self, args: dict):
        try:
            # Eight children per page bound open work; each child's failures remain independent.
            while True:
                children = await media_activity("batch_page", args)
                if not children:
                    await media_activity("finish_job", args)
                    return
                handles = []
                for child in children:
                    handles.append(
                        await workflow.start_child_workflow(
                            AssetWorkflow.run,
                            child,
                            id=child["workflow_id"],
                            task_queue=MEDIA_QUEUE,
                            parent_close_policy=workflow.ParentClosePolicy.ABANDON,
                        )
                    )
                await media_activity(
                    "ack_batch", {**args, "child_ids": [c["job_id"] for c in children]}
                )
                await asyncio.gather(*handles, return_exceptions=True)
                if (
                    workflow.info().is_continue_as_new_suggested()
                    or workflow.info().get_current_history_length() > 1000
                ):
                    workflow.continue_as_new(args)
        except asyncio.CancelledError:
            await report_failure(args, "canceled", "Batch canceled")
            raise
        except Exception as error:
            await report_failure(args, "failed", error)
            raise


@workflow.defn
class IndexWorkflow:
    @workflow.run
    async def run(self, args: dict):
        try:
            await workflow.execute_activity(
                "embed_asset",
                args,
                task_queue=INFERENCE_QUEUE,
                start_to_close_timeout=timedelta(minutes=30),
                heartbeat_timeout=timedelta(minutes=2),
                retry_policy=RETRY,
            )
            await media_activity("finish_job", args)
        except asyncio.CancelledError:
            await report_failure(args, "canceled", "Indexing canceled")
            raise
        except Exception as error:
            await report_failure(args, "failed", error)
            raise


@workflow.defn
class ExportWorkflow:
    @workflow.run
    async def run(self, args: dict):
        try:
            return await media_activity("render_export", args)
        except asyncio.CancelledError:
            await report_failure(args, "canceled", "Export canceled")
            raise
        except Exception as error:
            await report_failure(args, "failed", error)
            raise
