import asyncio
import hashlib
import json
from collections.abc import Awaitable
from contextlib import suppress
from uuid import UUID

from sqlalchemy import BigInteger, case, func, select
from sqlalchemy.dialects.postgresql import insert
from temporalio import activity

from rushes.config import settings
from rushes.credits import estimate_milli, reserve, settle
from rushes.db import tenant_session
from rushes.inference import (
    PREPROCESSING_VERSION,
    PROMPT_VERSION,
    SCHEMA_VERSION,
    AnalysisResponse,
    AnalysisResult,
    GeminiAnalyzer,
    ProviderPreparationError,
    analysis_cache_key,
    bounded_transcript,
    embedder,
    settle_analysis_result,
    validated_intervals,
)
from rushes.job_actions import cancel_batch_children
from rushes.maintenance import delete_remote
from rushes.models import (
    AnalysisRun,
    AnalysisWindow,
    Asset,
    Embedding,
    Export,
    Job,
    MediaTimeline,
    Observation,
    ProcessingEvent,
    Reservation,
    Shot,
    Usage,
)
from rushes.organization import ORGANIZATION_VERSION, category_records
from rushes.pipeline import ensure_prepared, prepare_asset, prepare_chunk, transcribe_asset
from rushes.provider_budget import ProviderBudgetError
from rushes.provider_files import record_provider_file
from rushes.storage import run_storage_thread, storage_activity
from rushes.timing import Interval, bounded_windows, to_us


def heartbeat(message="processing"):
    if activity.is_worker_shutdown():
        raise RuntimeError("Worker shutting down; resume this unit from its verified checkpoint")
    if activity.is_cancelled():
        raise asyncio.CancelledError()
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # Threaded media work checks cancellation; keep_alive sends heartbeats on the SDK loop.
        return
    activity.heartbeat(message)


async def keep_alive(awaitable: Awaitable):
    async def pulse():
        while True:
            heartbeat()
            await asyncio.sleep(10)

    task = asyncio.create_task(pulse())
    try:
        return await awaitable
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


async def stage(args: dict, message: str, progress: int):
    async with tenant_session(args["workspace_id"]) as db:
        job = await db.scalar(select(Job).where(Job.id == UUID(args["job_id"])).with_for_update())
        if job is None:
            raise ValueError("This job was deleted; no work can resume.")
        if job.state in {"failed", "canceled", "cancel_requested"}:
            raise asyncio.CancelledError()
        if job.state in {"completed", "ready", "partial"}:
            return
        if (job.stage, job.progress, job.state) != (message, progress, "running"):
            job.stage, job.progress, job.state = message, progress, "running"
            db.add(
                ProcessingEvent(
                    workspace_id=job.workspace_id, job_id=job.id, kind="stage", message=message
                )
            )


@activity.defn(name="prepare")
@storage_activity
async def prepare(args: dict):
    await stage(args, "Inspecting source and building preview", 10)
    return await keep_alive(prepare_asset(args["workspace_id"], args["asset_id"], heartbeat))


@activity.defn(name="transcribe")
@storage_activity
async def transcribe_activity(args: dict):
    await stage(args, "Transcribing available speech", 35)
    return await keep_alive(transcribe_asset(args["workspace_id"], args["asset_id"], heartbeat))


@activity.defn(name="plan_analysis")
async def plan_analysis(args: dict):
    heartbeat()
    config = settings()
    if not config.gemini_api_key or not config.gemini_api_key.get_secret_value():
        return {
            "run_id": None,
            "partial_reason": "Visual analysis needs a Gemini API key in local settings",
        }
    async with tenant_session(args["workspace_id"]) as db:
        job = await db.scalar(select(Job).where(Job.id == UUID(args["job_id"])).with_for_update())
        asset = await db.get(Asset, UUID(args["asset_id"]))
        operation = f"analysis:{job.id}"
        existing = await db.scalar(
            select(AnalysisRun).where(AnalysisRun.operation_key == operation)
        )
        if existing:
            pending = await db.scalar(
                select(AnalysisWindow.id)
                .where(
                    AnalysisWindow.run_id == existing.id,
                    AnalysisWindow.state.in_(["pending", "received"]),
                )
                .limit(1)
            )
            if pending:
                reservation = await db.scalar(
                    select(Reservation).where(Reservation.operation_key == operation)
                )
                await reserve(
                    db, asset.workspace_id, operation, reservation.amount_milli, resume=True
                )
            return {"run_id": str(existing.id)}
        confirmation = job.payload.get("analysis_confirmation")
        if confirmation and (
            confirmation["model"] != config.gemini_model
            or confirmation["fingerprint"] != asset.fingerprint
            or confirmation["amount_milli"] != estimate_milli(asset.duration_us)
        ):
            raise ValueError(
                "Analysis configuration changed after confirmation. Review a new estimate."
            )
        await reserve(db, asset.workspace_id, operation, estimate_milli(asset.duration_us))
        shots = list(await db.scalars(select(Shot.end_us).where(Shot.asset_id == asset.id)))
        run_digest = hashlib.sha256()
        run = AnalysisRun(
            workspace_id=asset.workspace_id,
            asset_id=asset.id,
            operation_key=operation,
            model=config.gemini_model,
            prompt_version=PROMPT_VERSION,
            preprocessing_version=PREPROCESSING_VERSION,
            schema_version=SCHEMA_VERSION,
            transcript_version="planning",
            sampling={
                "provider_default": True,
                "credits_per_minute": config.credits_per_minute,
                "chunk_max_seconds": config.analysis_window_seconds,
            },
            status="running",
        )
        db.add(run)
        await db.flush()
        for window in bounded_windows(
            asset.duration_us, shots, config.analysis_window_seconds * 1_000_000
        ):
            rows = list(
                await db.scalars(
                    select(Observation)
                    .where(
                        Observation.asset_id == asset.id,
                        Observation.kind == "speech",
                        Observation.producer == "faster-whisper",
                        Observation.start_us < window.end_us,
                        Observation.end_us > window.start_us,
                    )
                    .order_by(Observation.start_us, Observation.id)
                    .limit(100)
                )
            )
            snapshot = {
                "transcript": bounded_transcript("\n".join(row.description for row in rows)),
                "observation_versions": [
                    {
                        "id": str(row.id),
                        "version": row.version,
                        "start_us": row.start_us,
                        "end_us": row.end_us,
                    }
                    for row in rows
                ],
            }
            transcript_hash = hashlib.sha256(
                json.dumps(snapshot, sort_keys=True).encode()
            ).hexdigest()
            run_digest.update(transcript_hash.encode())
            cache = analysis_cache_key(
                fingerprint=asset.fingerprint,
                window=window,
                transcript_hash=transcript_hash,
                model=run.model,
                sampling=run.sampling,
                run_request=operation,
            )
            db.add(
                AnalysisWindow(
                    workspace_id=asset.workspace_id,
                    asset_id=asset.id,
                    run_id=run.id,
                    cache_key=cache,
                    input_snapshot=snapshot,
                    **window.model_dump(),
                )
            )
        run.transcript_version = run_digest.hexdigest()
        return {"run_id": str(run.id)}


@activity.defn(name="next_window")
async def next_window(args: dict):
    heartbeat()
    async with tenant_session(args["workspace_id"]) as db:
        window_id = await db.scalar(
            select(AnalysisWindow.id)
            .where(
                AnalysisWindow.run_id == UUID(args["run_id"]),
                AnalysisWindow.state.in_(["pending", "in_flight", "received"]),
            )
            .order_by(AnalysisWindow.start_us)
            .limit(1)
        )
        return str(window_id) if window_id else None


def compatible_inputs(run, window):
    if (run.prompt_version, run.preprocessing_version, run.schema_version) != (
        PROMPT_VERSION,
        PREPROCESSING_VERSION,
        SCHEMA_VERSION,
    ) or not window.input_snapshot:
        raise ValueError(
            "This analysis run uses incompatible or missing input provenance. Review a new analysis estimate."
        )


async def mark_ambiguous(db, window, reason):
    if window.state != "in_flight":
        return
    run = await db.get(AnalysisRun, window.run_id)
    window.state, window.error = "ambiguous", reason
    await db.execute(
        insert(Usage)
        .values(
            workspace_id=window.workspace_id,
            asset_id=window.asset_id,
            operation_key=f"ambiguous:{window.id}",
            kind="analysis_ambiguous",
            model=run.model,
            duration_us=window.end_us - window.start_us,
            attempts=window.attempts,
            provider_outcome="ambiguous",
        )
        .on_conflict_do_nothing()
    )


@activity.defn(name="prepare_window")
@storage_activity
async def prepare_window(args: dict):
    await stage(args, "Preparing a bounded analysis clip", 55)
    async with tenant_session(args["workspace_id"]) as db:
        window = await db.get(AnalysisWindow, UUID(args["window_id"]))
        if window.state != "pending":
            return
        compatible_inputs(await db.get(AnalysisRun, window.run_id), window)
        interval = Interval(start_us=window.start_us, end_us=window.end_us)
    await keep_alive(ensure_prepared(args["workspace_id"], args["asset_id"], heartbeat))
    await keep_alive(
        run_storage_thread(
            prepare_chunk, args["workspace_id"], args["asset_id"], interval, heartbeat
        )
    )


async def locked_window(db, id):
    return await db.scalar(
        select(AnalysisWindow).where(AnalysisWindow.id == UUID(str(id))).with_for_update()
    )


def effective_source_interval(mapping: dict, requested: Interval) -> Interval:
    return Interval(
        start_us=mapping["first_source_elapsed_us"],
        end_us=mapping.get("extracted_proxy", {}).get("end_us", requested.end_us),
    ).within(requested.end_us)


async def apply_received_response(args):
    async with tenant_session(args["workspace_id"]) as db:
        if args.get("job_id"):
            job = await db.scalar(
                select(Job).where(Job.id == UUID(args["job_id"])).with_for_update()
            )
            if job.state in {"failed", "canceled", "cancel_requested"}:
                return "received"
        window = await locked_window(db, args["window_id"])
        if window.state != "received":
            return window.state
        stored = window.raw_response
        result = AnalysisResult.model_validate({**stored["envelope"], "raw": stored["provider"]})
        if result.provider_reservation_id:
            try:
                await run_storage_thread(settle_analysis_result, result)
            except ProviderBudgetError as error:
                # Retry from this durable response; never send another generation.
                raise RuntimeError(
                    "Received analysis is waiting for spending reconciliation"
                ) from error
        interval = effective_source_interval(
            stored["chunk_mapping"], Interval(start_us=window.start_us, end_us=window.end_us)
        )
        asset = await db.get(Asset, window.asset_id)
        usage = await db.scalar(select(Usage).where(Usage.operation_key == f"analysis:{window.id}"))
        try:
            if result.validation_error:
                raise ValueError(result.validation_error)
            response = result.response or AnalysisResponse.model_validate_json(result.text or "")
            proposals = validated_intervals(response, interval, asset.duration_us)
        except ValueError:
            window.state = "failed"
            window.error = (
                result.validation_error
                or "Provider response was received but failed schema or interval validation. Raw response and measured usage are retained."
            )
            usage.provider_outcome = (
                "input_rejected"
                if result.provider_outcome == "input_rejected"
                else "invalid_response"
            )
            return "failed"
        source_timeline = await db.scalar(
            select(MediaTimeline).where(
                MediaTimeline.asset_id == asset.id, MediaTimeline.kind == "source"
            )
        )
        run = await db.get(AnalysisRun, window.run_id)
        for index, (proposed, absolute) in enumerate(proposals):
            attributes = (
                {
                    "organization_version": ORGANIZATION_VERSION,
                    "categories": category_records(proposed.categories),
                }
                if run.schema_version == SCHEMA_VERSION
                else {}
            )
            existing = await db.scalar(
                select(Observation.id)
                .where(
                    Observation.asset_id == asset.id,
                    Observation.run_id == window.run_id,
                    Observation.kind == proposed.kind,
                    Observation.description == proposed.description,
                    # Distinct supported labels must survive overlapping evidence deduplication.
                    Observation.attributes == attributes,
                    Observation.start_us < absolute.end_us,
                    Observation.end_us > absolute.start_us,
                )
                .limit(1)
            )
            if existing:
                continue
            db.add(
                Observation(
                    workspace_id=asset.workspace_id,
                    asset_id=asset.id,
                    timeline_id=source_timeline.id,
                    run_id=window.run_id,
                    window_id=window.id,
                    operation_key=f"analysis:{window.id}:{index}",
                    kind=proposed.kind,
                    start_us=absolute.start_us,
                    end_us=absolute.end_us,
                    proposed_start_us=interval.start_us + to_us(str(proposed.start_seconds)),
                    proposed_end_us=interval.start_us + to_us(str(proposed.end_seconds)),
                    description=proposed.description,
                    attributes=attributes,
                    evidence=[{"window_id": str(window.id)}],
                    producer="gemini",
                    model=result.model,
                    prompt_version=run.prompt_version,
                    preprocessing_version=run.preprocessing_version,
                    uncertainty=proposed.uncertainty,
                )
            )
        window.state, usage.provider_outcome = "completed", "confirmed"
        return "completed"


@activity.defn(name="analyze_window")
@storage_activity
async def analyze_window(args: dict):
    heartbeat()
    await stage(args, "Analyzing derived footage with Gemini", 65)
    async with tenant_session(args["workspace_id"]) as db:
        pending = await db.get(AnalysisWindow, UUID(args["window_id"]))
        old_file = pending.provider_file if pending and pending.state == "pending" else None
        old_expiry = pending.provider_file_expires_at if old_file else None
        previous = pending.raw_response if pending and pending.state == "pending" else None
    if previous and previous["envelope"].get("provider_reservation_id"):
        envelope = previous["envelope"]
        if envelope["provider_outcome"] in {"preparation_failed", "generation_rejected"}:
            # Finish accounting before a new response can replace the rejection evidence.
            await run_storage_thread(
                settle_analysis_result,
                AnalysisResult.model_validate({**envelope, "raw": previous["provider"]}),
            )
    if old_file:
        try:
            await run_storage_thread(delete_remote, old_file, old_expiry)
        except Exception as error:
            raise ProviderPreparationError(
                "The previous Google upload could not be cleaned up. No new analysis was sent; resume processing later."
            ) from error
        async with tenant_session(args["workspace_id"]) as db:
            pending = await locked_window(db, args["window_id"])
            if (
                pending.state == "pending"
                and pending.provider_file == old_file
                and pending.provider_file_expires_at == old_expiry
            ):
                record_provider_file(pending, None)
    async with tenant_session(args["workspace_id"]) as db:
        job = await db.scalar(select(Job).where(Job.id == UUID(args["job_id"])).with_for_update())
        if job.state in {"failed", "canceled", "cancel_requested"}:
            raise asyncio.CancelledError()
        window = await locked_window(db, args["window_id"])
        if window.state in {"completed", "ambiguous", "failed"}:
            return window.state
        if window.state == "in_flight":
            await mark_ambiguous(
                db,
                window,
                "A previous provider request may have succeeded. No automatic repeat was sent.",
            )
            return "ambiguous"
        received = window.state == "received"
        if not received:
            run = await db.get(AnalysisRun, window.run_id)
            compatible_inputs(run, window)
            transcript, run_model = window.input_snapshot["transcript"], run.model
            window.state = "in_flight"
            window.attempts += 1
            interval = Interval(start_us=window.start_us, end_us=window.end_us)
    if received:
        return await apply_received_response(args)
    chunk = None
    try:
        chunk = await keep_alive(
            run_storage_thread(
                prepare_chunk, args["workspace_id"], args["asset_id"], interval, heartbeat
            )
        )
        loop = asyncio.get_running_loop()

        async def save_upload(name, expires_at):
            async with tenant_session(args["workspace_id"]) as db:
                row = await locked_window(db, args["window_id"])
                record_provider_file(row, name, expires_at)

        def uploaded(name, expires_at):
            asyncio.run_coroutine_threadsafe(save_upload(name, expires_at), loop).result(timeout=30)

        chunk_plan = json.loads(
            await keep_alive(run_storage_thread(chunk.with_suffix(".timing.json").read_text))
        )
        effective_window = effective_source_interval(chunk_plan, interval)
        result = await keep_alive(
            run_storage_thread(
                GeminiAnalyzer(run_model).analyze, chunk, effective_window, transcript, uploaded
            )
        )
        if result.provider_outcome in {
            "budget_rejected",
            "preparation_failed",
            "generation_rejected",
        }:
            # Definitely unsent or explicitly rejected: retain the checkpoint without charging credits.
            async with tenant_session(args["workspace_id"]) as db:
                window = await locked_window(db, args["window_id"])
                if window.state == "in_flight":
                    window.raw_response = {
                        "provider": result.raw,
                        "envelope": result.model_dump(mode="json", exclude={"raw"}),
                        "chunk_mapping": chunk_plan,
                    }
                    window.state = "pending"
                    window.attempts -= 1
                    window.error = result.validation_error
                    record_provider_file(
                        window, result.cleanup_pending_file, result.cleanup_pending_file_expires_at
                    )
            error_type = (
                ProviderBudgetError
                if result.provider_outcome == "budget_rejected"
                else ProviderPreparationError
            )
            raise error_type(result.validation_error or "AI preparation unavailable")
        async with tenant_session(args["workspace_id"]) as db:
            window = await locked_window(db, args["window_id"])
            if window.state not in {"in_flight", "ambiguous"}:
                return window.state
            if window.state == "ambiguous":
                earlier = await db.scalar(
                    select(Usage).where(Usage.operation_key == f"ambiguous:{window.id}")
                )
                if earlier:
                    earlier.provider_outcome = "resolved_by_late_response"
                    earlier.duration_us = 0
            window.raw_response = {
                "provider": result.raw,
                "envelope": result.model_dump(mode="json", exclude={"raw"}),
                "chunk_mapping": chunk_plan,
            }
            record_provider_file(
                window, result.cleanup_pending_file, result.cleanup_pending_file_expires_at
            )
            window.state = "received"
            db.add(
                Usage(
                    workspace_id=window.workspace_id,
                    asset_id=window.asset_id,
                    operation_key=f"analysis:{window.id}",
                    kind="analysis_preflight"
                    if result.provider_outcome == "input_rejected"
                    else "analysis",
                    model=result.model,
                    duration_us=0
                    if result.provider_outcome == "input_rejected"
                    else effective_window.end_us - effective_window.start_us,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    attempts=0 if result.provider_outcome == "input_rejected" else window.attempts,
                    provider_outcome=result.provider_outcome,
                )
            )
        return await apply_received_response(args)
    finally:
        if chunk is not None:
            await keep_alive(run_storage_thread(chunk.unlink, missing_ok=True))


@activity.defn(name="embed_asset")
@storage_activity
async def embed_asset(args: dict):
    await stage(args, "Indexing worklog for search", 90)
    async with tenant_session(args["workspace_id"]) as db:
        job = await db.scalar(select(Job).where(Job.id == UUID(args["job_id"])).with_for_update())
        observation_ids = job.payload.get("observation_ids")
    cursor = None
    while True:
        async with tenant_session(args["workspace_id"]) as db:
            query = select(Observation).where(Observation.asset_id == UUID(args["asset_id"]))
            if observation_ids:
                query = query.where(Observation.id.in_([UUID(id) for id in observation_ids]))
            if cursor:
                query = query.where(Observation.id > cursor)
            rows = list(await db.scalars(query.order_by(Observation.id).limit(32)))
            if not rows:
                break
            texts = [
                (row.id, row.description, hashlib.sha256(row.description.encode()).hexdigest())
                for row in rows
            ]
            existing = {
                row.observation_id: row.text_hash
                for row in await db.scalars(
                    select(Embedding).where(
                        Embedding.observation_id.in_([row.id for row in rows]),
                        Embedding.model == settings().embedding_model,
                    )
                )
            }
            pending = [(id, text, hash) for id, text, hash in texts if existing.get(id) != hash]
            cursor = rows[-1].id
        if not pending:
            continue
        vectors = await keep_alive(
            run_storage_thread(
                lambda texts=[text for _, text, _ in pending]: embedder().embed(texts)
            )
        )
        async with tenant_session(args["workspace_id"]) as db:
            for (id, description, hash), vector in zip(pending, vectors, strict=True):
                current = await db.scalar(
                    select(Observation).where(Observation.id == id).with_for_update()
                )
                if current is None or current.description != description:
                    continue
                statement = insert(Embedding).values(
                    workspace_id=UUID(args["workspace_id"]),
                    observation_id=id,
                    model=settings().embedding_model,
                    dimension=len(vector),
                    text_hash=hash,
                    vector=vector,
                )
                await db.execute(
                    statement.on_conflict_do_update(
                        index_elements=["observation_id", "model"],
                        set_={"vector": vector, "dimension": len(vector), "text_hash": hash},
                    )
                )


async def finish_reservation(db, workspace_id, job_id, run_id):
    operation = f"analysis:{job_id}"
    reservation = await db.scalar(select(Reservation).where(Reservation.operation_key == operation))
    if reservation is None or reservation.state != "reserved":
        return
    mapping = AnalysisWindow.raw_response["chunk_mapping"]
    extracted_end = mapping["extracted_proxy"]["end_us"].as_string().cast(BigInteger)
    extracted_start = mapping["first_source_elapsed_us"].as_string().cast(BigInteger)
    windows = (
        list(
            await db.execute(
                select(
                    case(
                        (extracted_end.is_not(None), extracted_start),
                        else_=AnalysisWindow.start_us,
                    ).label("start_us"),
                    func.coalesce(
                        extracted_end,
                        AnalysisWindow.end_us,
                    ).label("end_us"),
                )
                .where(AnalysisWindow.run_id == run_id, AnalysisWindow.state == "completed")
                .order_by(AnalysisWindow.start_us)
            )
        )
        if run_id
        else []
    )
    covered, end = 0, 0
    for window in windows:
        covered += max(0, window.end_us - max(end, window.start_us))
        end = max(end, window.end_us)
    run = await db.get(AnalysisRun, run_id) if run_id else None
    rate = (
        run.sampling.get("credits_per_minute", settings().credits_per_minute)
        if run
        else settings().credits_per_minute
    )
    actual = (covered * rate * 1000 + 59_999_999) // 60_000_000
    await settle(db, workspace_id, operation, min(reservation.amount_milli, actual))


@activity.defn(name="finish_asset")
async def finish_asset(args: dict):
    heartbeat()
    async with tenant_session(args["workspace_id"]) as db:
        job = await db.scalar(select(Job).where(Job.id == UUID(args["job_id"])).with_for_update())
        asset = await db.get(Asset, UUID(args["asset_id"]))
        run_id = UUID(args["run_id"]) if args.get("run_id") else None
        incomplete = (
            await db.scalar(
                select(AnalysisWindow)
                .where(AnalysisWindow.run_id == run_id, AnalysisWindow.state != "completed")
                .order_by(AnalysisWindow.start_us)
                .limit(1)
            )
            if run_id
            else None
        )
        asset.status = "partial" if not run_id or incomplete else "ready"
        asset.error = args.get("partial_reason") or (
            (
                incomplete.error
                or f"Analysis is incomplete ({incomplete.state}); review the worklog and retry options."
            )
            if incomplete
            else None
        )
        if job.state in {"cancel_requested", "canceled"}:
            raise asyncio.CancelledError()
        job.state, job.stage, job.progress = asset.status, "Processing complete", 100
        await finish_reservation(db, asset.workspace_id, job.id, run_id)
        if run_id:
            (await db.get(AnalysisRun, run_id)).status = asset.status
        return {"state": asset.status}


async def finalize_failure(db, args):
    job = await db.scalar(select(Job).where(Job.id == UUID(args["job_id"])).with_for_update())
    if job is None or job.state in {"completed", "ready", "partial"}:
        return
    job.state = args["state"]
    job.error = args["error"]
    if job.kind == "batch":
        await cancel_batch_children(db, job.id)
    if job.kind == "export":
        output = await db.scalar(select(Export).where(Export.job_id == job.id))
        if output is not None:
            output.state = args["state"]
    if job.asset_id and job.kind == "asset":
        asset = await db.get(Asset, job.asset_id)
        asset.status = "partial" if asset.proxy_path else args["state"]
        asset.error = args["error"]
        run = await db.scalar(
            select(AnalysisRun).where(AnalysisRun.operation_key == f"analysis:{job.id}")
        )
        if run:
            windows = list(
                await db.scalars(
                    select(AnalysisWindow)
                    .where(
                        AnalysisWindow.run_id == run.id,
                        AnalysisWindow.state.in_(["in_flight", "received"]),
                    )
                    .with_for_update()
                )
            )
            for window in windows:
                if window.state == "received":
                    continue
                await mark_ambiguous(
                    db,
                    window,
                    "Processing ended with an unresolved provider request; no automatic repeat was sent.",
                )
            run.status = args["state"]
        await finish_reservation(db, job.workspace_id, job.id, run.id if run else None)


@activity.defn(name="fail_job")
async def fail_job(args: dict):
    async with tenant_session(args["workspace_id"]) as db:
        await finalize_failure(db, args)


@activity.defn(name="batch_page")
async def batch_page(args: dict):
    heartbeat()
    async with tenant_session(args["workspace_id"]) as db:
        jobs = list(
            await db.scalars(
                select(Job)
                .where(
                    Job.payload["batch_id"].astext == args["job_id"],
                    Job.kind == "asset",
                    Job.state == "queued",
                )
                .order_by(Job.created_at)
                .limit(8)
            )
        )
        result = []
        for job in jobs:
            result.append(
                {
                    "workspace_id": str(job.workspace_id),
                    "asset_id": str(job.asset_id),
                    "job_id": str(job.id),
                    "workflow_id": job.workflow_id,
                }
            )
        return result


@activity.defn(name="ack_batch")
async def ack_batch(args: dict):
    async with tenant_session(args["workspace_id"]) as db:
        for id in args["child_ids"]:
            job = await db.get(Job, UUID(id))
            if job.state == "queued":
                job.state = "dispatched"


@activity.defn(name="finish_job")
async def finish_job(args: dict):
    async with tenant_session(args["workspace_id"]) as db:
        job = await db.scalar(select(Job).where(Job.id == UUID(args["job_id"])).with_for_update())
        if job.state in {"canceled", "cancel_requested"}:
            raise asyncio.CancelledError()
        job.state, job.stage, job.progress = "completed", "Complete", 100


MEDIA_ACTIVITIES = [
    ack_batch,
    finish_job,
    prepare,
    transcribe_activity,
    plan_analysis,
    next_window,
    prepare_window,
    finish_asset,
    fail_job,
    batch_page,
]
INFERENCE_ACTIVITIES = [analyze_window, embed_asset]
