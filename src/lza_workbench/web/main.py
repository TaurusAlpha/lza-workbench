"""Local Uvicorn server entrypoint for the Web interface."""

from __future__ import annotations

from pathlib import Path

import uvicorn

from lza_workbench.web.app import create_app


def run_web_server(
    *,
    workspace_dir: Path,
    host: str,
    port: int,
    open_browser: bool,
) -> None:
    """Run the local Web server in the foreground."""
    url = f"http://{host}:{port}/"
    app = create_app(
        workspace_dir=workspace_dir,
        open_browser_url=url if open_browser else None,
    )
    uvicorn.run(app, host=host, port=port)
