import asyncio
import signal
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from rushes import api_lifespan, worker


class FakeWorker:
    def __init__(self, **options):
        self.on_fatal_error = options["on_fatal_error"]
        self.validate = asyncio.Event()
        self.validate.set()
        self.finish = asyncio.Event()
        self.finished = asyncio.Event()
        self.is_running = False
        self.validation_error = None
        self.drain_error = None
        self.shutdown_calls = 0

    async def run(self):
        await self.validate.wait()
        if self.validation_error:
            raise self.validation_error
        self.is_running = True
        try:
            await self.finish.wait()
        finally:
            self.is_running = False
            self.finished.set()
        if self.drain_error:
            raise self.drain_error

    async def shutdown(self):
        self.shutdown_calls += 1
        self.finish.set()
        # Like the SDK, validation failure leaves this event unset.
        await self.finished.wait()


@pytest.fixture
def fake_workers(monkeypatch):
    created = []

    def create(_client, **options):
        instance = FakeWorker(**options)
        created.append(instance)
        return instance

    async def background(*_args):
        await asyncio.Future()

    monkeypatch.setattr(worker.Client, "connect", AsyncMock(return_value=object()))
    monkeypatch.setattr(worker, "Worker", create)
    monkeypatch.setattr(worker, "dispatch", background)
    monkeypatch.setattr(worker, "maintain", background)
    return created


@pytest.fixture
def blocked_workers(fake_workers, monkeypatch):
    factory = worker.Worker

    def blocked(*args, **kwargs):
        instance = factory(*args, **kwargs)
        instance.validate.clear()
        return instance

    monkeypatch.setattr(worker, "Worker", blocked)
    return fake_workers


async def test_readiness_waits_for_namespace_validation(blocked_workers):
    fake_workers = blocked_workers
    entered, release = asyncio.Event(), asyncio.Event()

    async def use_workers():
        async with worker.running_workers():
            entered.set()
            await release.wait()

    task = asyncio.create_task(use_workers())
    try:
        async with asyncio.timeout(1):
            while len(fake_workers) < 2:
                await asyncio.sleep(0)
        assert not entered.is_set()
        for instance in fake_workers:
            instance.validate.set()
        await asyncio.wait_for(entered.wait(), 1)
    finally:
        release.set()
        for instance in fake_workers:
            instance.validate.set()
        await task
    assert [instance.shutdown_calls for instance in fake_workers] == [1, 1]


async def test_namespace_failure_does_not_wait_for_failed_worker_shutdown(
    fake_workers, monkeypatch
):
    factory = worker.Worker

    def invalid(*args, **kwargs):
        instance = factory(*args, **kwargs)
        if len(fake_workers) == 1:
            instance.validation_error = ValueError("Synthetic invalid namespace")
        return instance

    monkeypatch.setattr(worker, "Worker", invalid)
    async with asyncio.timeout(1):
        with pytest.raises(ValueError, match="Synthetic invalid namespace"):
            async with worker.running_workers():
                pytest.fail("Failed validation must not make the application ready")
    assert fake_workers[0].shutdown_calls == 0
    assert not fake_workers[1].is_running


async def test_shutdown_racing_validation_failure_finishes_without_hanging():
    instance = FakeWorker(on_fatal_error=None)
    instance.validate.clear()
    instance.validation_error = ValueError("Synthetic late validation failure")
    task = asyncio.create_task(instance.run())
    shutdown = asyncio.create_task(worker.stop_worker(instance, task))
    await asyncio.wait_for(instance.finish.wait(), 1)
    instance.validate.set()
    with pytest.raises(ValueError, match="Synthetic late validation"):
        await asyncio.wait_for(shutdown, 1)
    with pytest.raises(ValueError, match="Synthetic late validation"):
        await task


async def test_worker_connection_timeout_prevents_startup(fake_workers, monkeypatch):
    async def disconnected(*_args):
        await asyncio.Future()

    monkeypatch.setattr(worker.Client, "connect", disconnected)
    monkeypatch.setattr(worker, "STARTUP_TIMEOUT_SECONDS", 0.02)
    with pytest.raises(TimeoutError):
        async with worker.running_workers():
            pytest.fail("Disconnected workers must not become ready")
    assert fake_workers == []


async def test_validation_timeout_is_bounded(blocked_workers, monkeypatch):
    monkeypatch.setattr(worker, "STARTUP_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(worker, "SHUTDOWN_TIMEOUT_SECONDS", 0.02)
    async with asyncio.timeout(1):
        with pytest.raises(TimeoutError):
            async with worker.running_workers():
                pytest.fail("Unvalidated workers must not become ready")
    assert all(not instance.is_running for instance in blocked_workers)


async def test_failed_worker_does_not_cancel_healthy_companion_drain(fake_workers):
    release, shutdown_started = asyncio.Event(), asyncio.Event()
    context = worker.running_workers()
    tasks = await context.__aenter__()
    fake_workers[0].drain_error = RuntimeError("Synthetic failure after drain")
    companion = fake_workers[1]

    async def slow_shutdown():
        shutdown_started.set()
        await release.wait()
        companion.finish.set()
        await companion.finished.wait()

    companion.shutdown = slow_shutdown
    closing = asyncio.create_task(context.__aexit__(None, None, None))
    try:
        await asyncio.wait_for(shutdown_started.wait(), 1)
        await asyncio.wait_for(fake_workers[0].finished.wait(), 1)
        await asyncio.sleep(0)
        assert not closing.done()
        assert not tasks[1].done()
    finally:
        release.set()
        with pytest.raises(RuntimeError, match="Synthetic failure after drain"):
            await asyncio.wait_for(closing, 1)
    assert not tasks[1].cancelled()


async def test_shutdown_deadline_does_not_wait_for_cancellation_resistant_activity(
    fake_workers, monkeypatch
):
    monkeypatch.setattr(worker, "SHUTDOWN_TIMEOUT_SECONDS", 0.02)
    release, canceled = asyncio.Event(), asyncio.Event()
    factory = worker.Worker

    def draining(*args, **kwargs):
        instance = factory(*args, **kwargs)

        async def run():
            instance.is_running = True
            try:
                while not release.is_set():
                    try:
                        await release.wait()
                    except asyncio.CancelledError:
                        canceled.set()
            finally:
                instance.is_running = False
                instance.finished.set()

        instance.run = run
        return instance

    monkeypatch.setattr(worker, "Worker", draining)
    tasks = []
    try:
        async with asyncio.timeout(0.5):
            with pytest.raises(TimeoutError, match="drain deadline"):
                async with worker.running_workers() as tasks:
                    pass
        await asyncio.wait_for(canceled.wait(), 1)
        assert not release.is_set()
        assert any(not task.done() for task in tasks[:2])
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)


async def test_fatal_error_is_visible_before_worker_drain_finishes(fake_workers):
    async with worker.running_workers() as tasks:
        await fake_workers[0].on_fatal_error(RuntimeError("Synthetic fatal worker error"))
        assert all(instance.is_running for instance in fake_workers)
        with pytest.raises(RuntimeError, match="Synthetic fatal worker error"):
            await tasks[-1]
    assert all(not instance.is_running for instance in fake_workers)


async def test_api_only_mode_does_not_start_workers(monkeypatch):
    monkeypatch.setattr(
        api_lifespan, "settings", lambda: SimpleNamespace(host_workflow_service=False)
    )

    def unexpected():
        pytest.fail("API-only mode must not start workers")

    monkeypatch.setattr(worker, "running_workers", unexpected)
    async with api_lifespan.lifespan(None):
        pass


@pytest.mark.parametrize("outcome", ["error", "canceled", "returned", "normal_shutdown"])
async def test_worker_failure_requests_one_api_shutdown(monkeypatch, outcome):
    monkeypatch.setattr(
        api_lifespan, "settings", lambda: SimpleNamespace(host_workflow_service=True)
    )
    tasks = [asyncio.get_running_loop().create_future() for _ in range(2)]

    @asynccontextmanager
    async def running():
        try:
            yield tasks
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    signals = []
    monkeypatch.setattr(worker, "running_workers", running)
    monkeypatch.setattr(api_lifespan.os, "kill", lambda pid, sig: signals.append(sig))
    async with api_lifespan.lifespan(None):
        if outcome == "error":
            tasks[0].set_exception(RuntimeError("Synthetic worker failure"))
        elif outcome == "canceled":
            tasks[0].cancel()
        elif outcome == "returned":
            tasks[0].set_result(None)
        if outcome != "normal_shutdown":
            tasks[1].set_result(None)
        await asyncio.sleep(0)
    assert signals == ([] if outcome == "normal_shutdown" else [signal.SIGTERM])
