"""Content-free JSON spans. Activities emit on execution, never on workflow replay.

Set RUSHES_TRACE_FILE to an operator-owned JSONL path for benchmark collection.
Otherwise spans use the rushes.trace logger. No media paths, queries, or model text
are recorded. Lost process end spans are intentionally left open after SIGKILL.
"""

import hashlib
import inspect
import json
import logging
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from uuid import uuid4

from temporalio import activity
from temporalio.worker import ActivityInboundInterceptor, Interceptor

_context = ContextVar("rushes_trace", default=None)
logger = logging.getLogger("rushes.trace")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())
logger.propagate = False


def job_trace_id(job_id):
    return hashlib.sha256(str(job_id).encode()).hexdigest()[:32]


def context():
    return dict(_context.get() or {})


def emit(record):
    line = json.dumps({"schema": 1, **record}, separators=(",", ":"))
    try:
        path = os.environ.get("RUSHES_TRACE_FILE")
        if path:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(descriptor, (line + "\n").encode())
            finally:
                os.close(descriptor)
        else:
            logger.info(line)
    except OSError:
        # Telemetry must not turn a committed activity into a retry.
        logger.warning("Trace sink unavailable")


@contextmanager
def span(name, **attributes):
    parent = context()
    trace_id = attributes.pop("trace_id", None) or parent.get("trace_id") or uuid4().hex
    current = {**parent, "trace_id": trace_id, "span_id": uuid4().hex[:16]}
    current.update(attributes)
    token = _context.set(current)
    started = time.perf_counter_ns()
    base = {**current, "parent_span_id": parent.get("span_id"), "name": name}
    emit({**base, "event": "start", "time_ns": time.time_ns()})
    status = "ok"
    try:
        yield current
    except BaseException as error:
        status = type(error).__name__
        raise
    finally:
        emit(
            {
                **base,
                "event": "end",
                "time_ns": time.time_ns(),
                "duration_ns": time.perf_counter_ns() - started,
                "status": status,
            }
        )
        _context.reset(token)


def traced(name):
    def decorate(function):
        if inspect.iscoroutinefunction(function):

            @wraps(function)
            async def asynchronous(*args, **kwargs):
                with span(name):
                    return await function(*args, **kwargs)

            return asynchronous

        @wraps(function)
        def synchronous(*args, **kwargs):
            with span(name):
                return function(*args, **kwargs)

        return synchronous

    return decorate


class TraceActivities(ActivityInboundInterceptor):
    async def execute_activity(self, input):
        info = activity.info()
        args = input.args[0] if input.args and isinstance(input.args[0], dict) else {}
        logical_job = args.get("job_id", info.workflow_id)
        trace = args.get("trace_context", {})
        token = _context.set(trace)
        try:
            with span(
                "activity." + info.activity_type,
                trace_id=trace.get("trace_id") or job_trace_id(logical_job),
                job_id=logical_job,
                asset_id=args.get("asset_id"),
                workflow_id=info.workflow_id,
                workflow_run_id=info.workflow_run_id,
                activity_id=info.activity_id,
                attempt=info.attempt,
                queue=info.task_queue,
                queue_wait_ns=max(
                    0,
                    int(
                        (info.started_time - info.current_attempt_scheduled_time).total_seconds()
                        * 1e9
                    ),
                ),
                scheduled_to_start_ns=max(
                    0, int((info.started_time - info.scheduled_time).total_seconds() * 1e9)
                ),
            ):
                return await super().execute_activity(input)
        finally:
            _context.reset(token)


class TraceInterceptor(Interceptor):
    def intercept_activity(self, next):
        return TraceActivities(next)


class TraceBoundary:
    """W3C traceparent correlation only; never used for identity or authorization."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").endswith(
            ("/upload", "/search", "/export-preview", "/start")
        ):
            return await self.app(scope, receive, send)
        import re

        headers = dict(scope.get("headers", []))
        value = headers.get(b"traceparent", b"").decode("ascii", errors="ignore")
        match = re.fullmatch(r"00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})", value)
        incoming = {}
        if match and int(match[1], 16) and int(match[2], 16):
            incoming = {"trace_id": match[1], "span_id": match[2]}
        token = _context.set(incoming)
        try:
            with span("http.request", method=scope["method"]):
                await self.app(scope, receive, send)
        finally:
            _context.reset(token)
