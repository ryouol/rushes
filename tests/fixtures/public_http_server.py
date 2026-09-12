"""Real HTTP server fixture; synthetic responses and no database/provider access."""

import asyncio
import sys

import uvicorn
from fastapi import FastAPI, Request
from rushes.frontend import Frontend
from rushes.http_protocol import ReceiveDeadlineProtocol
from rushes.security import CallbackLogBoundary
from starlette.responses import Response, StreamingResponse

port = int(sys.argv[1])
api = FastAPI()


@api.get("/api/health")
async def health():
    return {"ok": True}


@api.post("/api/body")
@api.post("/api/workspaces/test/projects/test/upload")
async def body(request: Request):
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
    return {"received": received}


@api.get("/api/events")
async def events():
    async def stream():
        yield b"data: first\n\n"
        await asyncio.sleep(.6)
        yield b"data: second\n\n"
    return StreamingResponse(stream(), media_type="text/event-stream")


@api.post("/api/reject")
async def reject():
    return Response(status_code=403)


@api.get("/api/auth/google/callback")
async def callback(request: Request):
    return {"received": bool(request.query_params.get("code"))}


ReceiveDeadlineProtocol.header_timeout = 1
ReceiveDeadlineProtocol.body_timeout = .3
uvicorn.run(
    CallbackLogBoundary(Frontend(api, origin=f"http://localhost:{port}")),
    host="127.0.0.1", port=port, http=ReceiveDeadlineProtocol, ws="none", proxy_headers=False,
    timeout_graceful_shutdown=1,
    limit_concurrency=4,
)
