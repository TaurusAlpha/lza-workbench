"""Local Uvicorn server entrypoint for the Web interface."""

from __future__ import annotations

from pathlib import Path

import uvicorn

from lza_workbench.interfaces.web.app import create_app


def run_web_server(
    *,
    workspace_dir: Path | None = None,
    host: str,
    port: int,
    open_browser: bool,
    dev: bool = False,
) -> None:
    url = f"http://{host}:{port}/"

    if open_browser:
        import threading
        import time
        import urllib.request
        import webbrowser

        def _open_when_ready() -> None:
            check_url = f"http://{host}:{port}/api/workspace/active"
            for _ in range(40):
                time.sleep(0.15)
                try:
                    with urllib.request.urlopen(check_url, timeout=0.5):
                        webbrowser.open(url)
                        return
                except Exception:
                    pass

        threading.Thread(target=_open_when_ready, daemon=True).start()

    if dev:
        import os

        if workspace_dir is not None:
            os.environ["LZA_DEV_WORKSPACE_DIR"] = str(workspace_dir.resolve())
        else:
            os.environ.pop("LZA_DEV_WORKSPACE_DIR", None)

        src_dir = Path(__file__).resolve().parents[2]
        uvicorn.run(
            "lza_workbench.interfaces.web.app:create_dev_app",
            factory=True,
            host=host,
            port=port,
            reload=True,
            reload_dirs=[str(src_dir)],
            timeout_graceful_shutdown=1,
        )
    else:
        app = create_app(
            workspace_dir=workspace_dir,
            dev_mode=False,
        )
        uvicorn.run(app, host=host, port=port)


