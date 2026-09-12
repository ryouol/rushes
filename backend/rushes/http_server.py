"""Serve the public application, or its API boundary behind the local development server."""

import argparse
import json
import os
from pathlib import Path

import uvicorn

from rushes.config import settings
from rushes.frontend import Frontend
from rushes.http_protocol import ReceiveDeadlineProtocol
from rushes.security import CallbackLogBoundary


def verify_public_config(root: Path, expected: dict[str, str]):
    try:
        built = json.loads((root / "build-config.json").read_text())
    except (OSError, ValueError) as error:
        raise RuntimeError("Build the web application before starting the public server") from error
    if built != expected:
        raise RuntimeError("Public web configuration changed. Rebuild the web application before starting it")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=os.environ.get("PORT", "3741"))
    parser.add_argument("--host", default=os.environ.get("RUSHES_BIND_HOST", "127.0.0.1"))
    parser.add_argument("--api-only", action="store_true")
    parser.add_argument("--static-root", type=Path, default=Path("web/out"))
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    config = settings()
    root = None if args.api_only else args.static_root
    if root is not None:
        verify_public_config(root, config.public_web_config)
    from rushes.api import app

    uvicorn.run(
        CallbackLogBoundary(Frontend(
            app, origin=config.origin, client_ip_header=config.client_ip_header or "", root=root,
        )),
        host=args.host,
        port=args.port,
        http=ReceiveDeadlineProtocol,
        ws="none",
        proxy_headers=False,
        timeout_graceful_shutdown=10,
        limit_concurrency=64,
        server_header=False,
    )


if __name__ == "__main__":
    main()
