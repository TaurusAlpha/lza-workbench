"""Development mode endpoints and live-reload event streaming."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

STATIC_DIR = Path(__file__).parent / "static"
SERVER_INSTANCE_ID = uuid.uuid4().hex


def _get_latest_static_mtime() -> float:
    latest = 0.0
    if not STATIC_DIR.is_dir():
        return latest
    for path in STATIC_DIR.rglob("*"):
        if path.is_file():
            try:
                latest = max(latest, path.stat().st_mtime)
            except OSError:
                continue
    return latest


DEV_SHUTDOWN_EVENT: asyncio.Event | None = None


def get_dev_shutdown_event() -> asyncio.Event:
    global DEV_SHUTDOWN_EVENT
    if DEV_SHUTDOWN_EVENT is None:
        DEV_SHUTDOWN_EVENT = asyncio.Event()
    return DEV_SHUTDOWN_EVENT


def create_dev_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/dev/live-reload")
    async def live_reload(request: Request) -> StreamingResponse:
        async def event_generator():
            shutdown_event = get_dev_shutdown_event()
            yield f"event: init\ndata: {json.dumps({'serverId': SERVER_INSTANCE_ID})}\n\n"
            last_mtime = _get_latest_static_mtime()
            ping_counter = 0

            while not shutdown_event.is_set():
                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=0.3)
                    break
                except (asyncio.TimeoutError, TimeoutError):
                    pass

                if await request.is_disconnected():
                    break

                current_mtime = _get_latest_static_mtime()
                if current_mtime > last_mtime:
                    last_mtime = current_mtime
                    yield f"event: reload\ndata: {json.dumps({'reason': 'static_modified'})}\n\n"

                ping_counter += 1
                if ping_counter >= 50:  # send keepalive every ~15 seconds
                    ping_counter = 0
                    yield ": ping\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return router
