import asyncio
import threading
import uuid
from contextlib import contextmanager

import pytest
from rushes import storage
from rushes.config import settings


async def test_cancel_during_lease_acquisition_releases_the_completed_lease(monkeypatch, tmp_path):
    monkeypatch.setattr(settings(), "storage_root", tmp_path)
    workspace = uuid.uuid4()
    entered, release = threading.Event(), threading.Event()
    original = storage.workspace_file_lease

    @contextmanager
    def slow_lease(*args, **kwargs):
        with original(*args, **kwargs):
            entered.set()
            assert release.wait(3), "Lease acquisition blocked the event loop"
            yield

    monkeypatch.setattr(storage, "workspace_file_lease", slow_lease)

    @storage.storage_activity
    async def unused(_args):
        pytest.fail("Canceled acquisition must not start the activity")

    task = asyncio.create_task(unused({"workspace_id": str(workspace)}))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
    with original(workspace, exclusive=True):
        pass
