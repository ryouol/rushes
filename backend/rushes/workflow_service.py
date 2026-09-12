"""Private single-host Temporal service configuration and readiness."""

import argparse
import asyncio
import json
import os
import time
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from google.protobuf.duration_pb2 import Duration
from sqlalchemy.engine import URL, make_url
from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest, RegisterNamespaceRequest
from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode

from rushes.config import Settings, settings


def database_urls(config: Settings):
    values = (config.temporal_database_url, config.temporal_visibility_database_url)
    if not all(values):
        raise ValueError(
            "Hosted Temporal requires separate workflow and visibility PostgreSQL URLs"
        )
    urls = [make_url(value.get_secret_value()) for value in values]
    app_url = make_url(config.database_url.get_secret_value())
    identities = [url.database for url in [app_url, *urls]]
    if any(name and "%" in name for name in identities):
        raise ValueError("Database names must be literal and cannot contain percent encoding")
    if len(set(identities)) != 3:
        raise ValueError("Application, workflow and visibility must use distinct database names")
    for url in urls:
        if url.drivername not in {"postgresql", "postgresql+psycopg"} or not all(
            (url.host, url.database, url.username, url.password)
        ):
            raise ValueError("Temporal databases require complete PostgreSQL URLs")
        if set(url.query) - {"sslmode", "sslrootcert"} or url.query.get(
            "sslmode", "verify-full"
        ) not in {
            "disable",
            "require",
            "verify-full",
        }:
            raise ValueError(
                "Temporal URLs support sslmode=disable, require or verify-full and sslrootcert"
            )
        ca = url.query.get("sslrootcert", "system")
        if ca != "system" and not Path(ca).is_absolute():
            raise ValueError("Temporal sslrootcert must be system or an absolute CA-file path")
    return urls


def database_tls(url: URL) -> dict:
    mode = url.query.get("sslmode", "verify-full")
    ca = url.query.get("sslrootcert", "system")
    return {
        "enabled": mode != "disable",
        "enableHostVerification": mode == "verify-full",
        "serverName": url.host,
        "caFile": "" if ca == "system" else ca,
    }


def server_config(config: Settings) -> dict:
    if config.temporal_address != "127.0.0.1:7233":
        raise ValueError("Hosted Temporal must use the private loopback address 127.0.0.1:7233")
    stores = {}
    for name, url in zip(("default", "visibility"), database_urls(config), strict=True):
        host = f"[{url.host}]" if ":" in url.host else url.host
        stores[name] = {
            "sql": {
                "pluginName": "postgres12",
                "databaseName": url.database,
                "connectAddr": f"{host}:{url.port or 5432}",
                "connectProtocol": "tcp",
                "user": url.username,
                "password": url.password,
                "maxConns": 3,
                "maxIdleConns": 1,
                "maxConnLifetime": "5m",
                "tls": database_tls(url),
            }
        }
    return {
        "log": {"stdout": True, "level": "warn"},
        "persistence": {
            "numHistoryShards": 4,
            "defaultStore": "default",
            "visibilityStore": "visibility",
            "datastores": stores,
        },
        "global": {"membership": {"maxJoinDuration": "30s", "broadcastAddress": "127.0.0.1"}},
        "services": {
            name: {"rpc": {"grpcPort": port, "membershipPort": port - 300, "bindOnIP": "127.0.0.1"}}
            for name, port in (
                ("frontend", 7233),
                ("history", 7234),
                ("matching", 7235),
                ("worker", 7239),
            )
        },
        "clusterMetadata": {
            "enableGlobalNamespace": False,
            "failoverVersionIncrement": 10,
            "masterClusterName": "active",
            "currentClusterName": "active",
            "clusterInformation": {
                "active": {
                    "enabled": True,
                    "initialFailoverVersion": 1,
                    "rpcName": "frontend",
                    "rpcAddress": "127.0.0.1:7233",
                }
            },
        },
        "dcRedirectionPolicy": {"policy": "noop"},
        "archival": {"history": {"state": "disabled"}, "visibility": {"state": "disabled"}},
    }


def write_server_config(config: Settings, path: Path):
    # JSON is valid YAML and safely quotes arbitrary database credentials.
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as output:
        json.dump(server_config(config), output)


async def wait_for_namespace(
    address: str, *, timeout: float = 60, stopping: Callable[[], bool] = lambda: False
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if stopping():
            return False
        try:
            client = await asyncio.wait_for(Client.connect(address), timeout=3)
            if not await client.service_client.check_health(timeout=timedelta(seconds=3)):
                await asyncio.sleep(0.5)
                continue
            try:
                await client.workflow_service.describe_namespace(
                    DescribeNamespaceRequest(namespace="default"), timeout=timedelta(seconds=3)
                )
            except RPCError as error:
                if error.status != RPCStatusCode.NOT_FOUND:
                    raise
                try:
                    await client.workflow_service.register_namespace(
                        RegisterNamespaceRequest(
                            namespace="default",
                            description="RUSHES workflow execution",
                            workflow_execution_retention_period=Duration(seconds=3 * 86400),
                        ),
                        timeout=timedelta(seconds=3),
                    )
                except RPCError as conflict:
                    if conflict.status != RPCStatusCode.ALREADY_EXISTS:
                        raise
                await asyncio.sleep(1)
                continue
            return True
        except (RuntimeError, TimeoutError, RPCError):
            await asyncio.sleep(0.5)
    raise TimeoutError("Private Temporal service and default namespace did not become ready")


def prepare_service(path: Path) -> dict:
    config = settings()
    if config.origin.startswith("https:") and not config.client_ip_header:
        raise ValueError(
            "Set RUSHES_CLIENT_IP_HEADER to a header overwritten by the trusted ingress"
        )
    for folder in (config.storage_root, config.output_root):
        folder.mkdir(parents=True, exist_ok=True)
    if config.host_workflow_service:
        write_server_config(config, path)
    return {
        "host_workflow_service": config.host_workflow_service,
        "upload_timeout_seconds": config.upload_timeout_seconds,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare").add_argument("path", type=Path)
    commands.add_parser("wait")
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare_service(args.path)
    else:
        result = asyncio.run(wait_for_namespace(settings().temporal_address))
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
