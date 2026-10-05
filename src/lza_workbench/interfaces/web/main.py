"""Local Uvicorn server entrypoint for the Web interface."""

from __future__ import annotations

from pathlib import Path

import uvicorn

from lza_workbench.interfaces.web.app import create_app


def run_web_server(
    *,
    workspace_dir: Path,
    host: str,
    port: int,
    open_browser: bool,
    dev: bool = False,
) -> None:
    url = f"http://{host}:{port}/"
    if dev:
        import os

        os.environ["LZA_DEV_WORKSPACE_DIR"] = str(workspace_dir.resolve())
        if open_browser:
            os.environ["LZA_DEV_BROWSER_URL"] = url

        src_dir = Path(__file__).resolve().parents[2]
        uvicorn.run(
            "lza_workbench.interfaces.web.app:create_dev_app",
            factory=True,
            host=host,
            port=port,
            reload=True,
            reload_dirs=[str(src_dir)],
        )
    else:
        app = create_app(
            workspace_dir=workspace_dir,
            open_browser_url=url if open_browser else None,
            dev_mode=False,
        )
        uvicorn.run(app, host=host, port=port)

