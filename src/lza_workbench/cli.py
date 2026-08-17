"""Compatibility entrypoint for LZA Workbench CLI (to be removed in Step 16)."""

from __future__ import annotations

from lza_workbench.cli.main import app, main

__all__ = ["app", "main"]

if __name__ == "__main__":
    raise SystemExit(main())
