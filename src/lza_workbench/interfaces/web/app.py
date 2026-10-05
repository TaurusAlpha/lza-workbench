"""FastAPI application factory for the local Workbench interface."""

from __future__ import annotations

import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from lza_workbench.errors import LzaError
from lza_workbench.interfaces.web.status import ActiveWorkspaceContext, create_status_router
from lza_workbench.interfaces.web.uninstall import create_uninstall_router

STATIC_DIR = Path(__file__).parent / "static"


def create_app(
    *,
    workspace_dir: Path | ActiveWorkspaceContext | None = None,
    open_browser_url: str | None = None,
    dev_mode: bool = False,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        import os

        if open_browser_url and not os.environ.get("LZA_BROWSER_OPENED"):
            os.environ["LZA_BROWSER_OPENED"] = "1"
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
        else ActiveWorkspaceContext(workspace_dir, dev_mode=dev_mode)
    )

    app.include_router(create_status_router(workspace_dir=context))
    app.include_router(create_uninstall_router(workspace_dir=context))
    if context.dev_mode:
        from lza_workbench.interfaces.web.dev import create_dev_router

        app.include_router(create_dev_router())
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


def create_dev_app() -> FastAPI:
    """Application factory for Uvicorn development reload mode."""
    import os

    workspace_raw = os.environ.get("LZA_DEV_WORKSPACE_DIR")
    workspace_dir = Path(workspace_raw) if workspace_raw else None
    browser_url = os.environ.get("LZA_DEV_BROWSER_URL")
    return create_app(
        workspace_dir=workspace_dir,
        open_browser_url=browser_url,
        dev_mode=True,
    )

