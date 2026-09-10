import asyncio
import json
import signal
import stat

import pytest
from pydantic import SecretStr
from rushes.config import Settings, settings
from rushes.workflow_service import (
    database_urls,
    server_config,
    wait_for_namespace,
    write_server_config,
)


def configured(**changes):
    return Settings.model_validate(
        {
            **settings().model_dump(),
            "database_url": "postgresql://app:synthetic@db/app",
            "temporal_database_url": "postgresql://workflow:synthetic@db/workflow",
            "temporal_visibility_database_url": "postgresql://workflow:synthetic@db/visibility",
            **changes,
        }
    )


def test_separate_database_configuration_is_required():
    for override in (
        {"temporal_database_url": None},
        {"temporal_database_url": "postgresql://workflow:synthetic@db/app"},
        {"temporal_database_url": "postgresql://workflow:synthetic@DB/app"},
        {"temporal_database_url": "postgresql://workflow:synthetic@alias/app"},
        {"temporal_database_url": "postgresql://workflow:synthetic@db/%61pp"},
        {"temporal_database_url": "postgresql://workflow:synthetic@db/%77orkflow"},
        {"database_url": "postgresql://app:synthetic@db/%61pp"},
        {"temporal_visibility_database_url": "postgresql://workflow:synthetic@db/workflow"},
        {"temporal_database_url": "sqlite:///workflow"},
        {"temporal_database_url": "postgresql://workflow:synthetic@db/workflow?sslmode=prefer"},
    ):
        with pytest.raises(ValueError):
            database_urls(configured(**override))
    with pytest.raises(ValueError, match="loopback"):
        server_config(configured(temporal_address="0.0.0.0:7233"))


def test_private_config_safely_serializes_credentials_and_verified_tls(tmp_path):
    from sqlalchemy.engine import make_url

    config = configured()
    url = make_url(config.temporal_database_url.get_secret_value()).set(
        password='quoted"\\\ncredential'
    )
    config.temporal_database_url = SecretStr(url.render_as_string(hide_password=False))
    file = tmp_path / "temporal.yaml"
    write_server_config(config, file)
    actual = json.loads(file.read_text())
    assert stat.S_IMODE(file.stat().st_mode) == 0o600
    assert (
        actual["persistence"]["datastores"]["default"]["sql"]["password"] == 'quoted"\\\ncredential'
    )
    for store in actual["persistence"]["datastores"].values():
        assert store["sql"]["tls"] == {
            "enabled": True,
            "enableHostVerification": True,
            "serverName": "db",
            "caFile": "",
        }
    assert all(service["rpc"]["bindOnIP"] == "127.0.0.1" for service in actual["services"].values())


async def test_shutdown_does_not_attempt_namespace_connection(monkeypatch):
    from rushes import workflow_service

    async def unexpected(*args, **kwargs):
        pytest.fail("Shutdown must not connect or register a namespace")

    monkeypatch.setattr(workflow_service.Client, "connect", unexpected)
    assert not await wait_for_namespace("127.0.0.1:7233", stopping=lambda: True)


async def test_shutdown_stops_polling_both_queues_before_waiting_for_drain(monkeypatch):
    from rushes import worker

    entered = asyncio.Event()
    drained = asyncio.Event()
    queues = []
    signals = {}

    class ActiveQueue:
        def __init__(self, *args, **kwargs):
            self.stopped_polling = asyncio.Event()
            queues.append(self)

        async def __aenter__(self):
            if len(queues) == 2:
                entered.set()
            return self

        async def shutdown(self):
            self.stopped_polling.set()
            await drained.wait()

        async def __aexit__(self, *args):
            await self.shutdown()

    async def connect(*args, **kwargs):
        return object()

    async def idle(*args):
        await asyncio.Event().wait()

    monkeypatch.setattr(worker, "Worker", ActiveQueue)
    monkeypatch.setattr(worker.Client, "connect", connect)
    monkeypatch.setattr(worker, "dispatch", idle)
    monkeypatch.setattr(worker, "maintain", idle)
    monkeypatch.setattr(
        asyncio.get_running_loop(),
        "add_signal_handler",
        lambda sig, callback: signals.update({sig: callback}),
    )
    running = asyncio.create_task(worker.main())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        signals[signal.SIGTERM]()
        await asyncio.wait_for(
            asyncio.gather(*(queue.stopped_polling.wait() for queue in queues)), 1
        )
    finally:
        drained.set()
        await asyncio.wait_for(running, 1)
