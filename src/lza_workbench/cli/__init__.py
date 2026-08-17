"""CLI package for LZA Workbench."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lza_workbench.cli.main import app, main


def __getattr__(name: str):
    if name in ("app", "main"):
        from lza_workbench.cli.main import app, main

        globals()["app"] = app
        globals()["main"] = main
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["app", "main"]
