"""FastAPI application factory for the local Workbench interface."""

from __future__ import annotations

import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from lza_workbench.errors import LzaError
from lza_workbench.web.status import ActiveWorkspaceContext, create_status_router

STATIC_DIR = Path(__file__).parent / "static"


def create_app(
    *,
    workspace_dir: Path | ActiveWorkspaceContext | None = None,
    open_browser_url: str | None = None,
) -> FastAPI:
    """Create the local Web interface for workspaces."""

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if open_browser_url:
            webbrowser.open(open_browser_url)
        yield

    app = FastAPI(title="LZA Workbench", lifespan=lifespan)

    @app.exception_handler(LzaError)
    async def handle_lza_error(_: Request, exc: LzaError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "workspace_unavailable", "message": str(exc)}},
        )

    context = (
        workspace_dir
        if isinstance(workspace_dir, ActiveWorkspaceContext)
        else ActiveWorkspaceContext(workspace_dir)
    )

    app.include_router(create_status_router(workspace_dir=context))
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
