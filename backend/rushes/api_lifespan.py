import logging
import os
import signal
from contextlib import asynccontextmanager

from rushes.config import settings

logger = logging.getLogger("rushes.runtime")


@asynccontextmanager
async def lifespan(_app):
    if not settings().host_workflow_service:
        yield
        return

    from rushes.worker import running_workers

    closing = False

    def worker_finished(task):
        nonlocal closing
        if not closing:
            closing = True
            error = None if task.cancelled() else task.exception()
            logger.critical("A RUSHES worker task stopped unexpectedly", exc_info=error)
            os.kill(os.getpid(), signal.SIGTERM)

    async with running_workers() as tasks:
        for task in tasks:
            task.add_done_callback(worker_finished)
        try:
            yield
        finally:
            closing = True
            for task in tasks:
                task.remove_done_callback(worker_finished)
