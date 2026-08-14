"""Shared utility functions."""

from __future__ import annotations

from pathlib import Path

import typer

from lza_workbench.core.errors import LzaError


def normalize_path(path: Path) -> Path:
    """Consistently expand user home directory and resolve path."""
    return path.expanduser().resolve()


def value_or_prompt(label: str, value: str | None, default: str | None, interactive: bool) -> str:
    """Use an explicit value, prompt with a default, or use that default."""
    if value:
        return value
    if interactive:
        if default is not None:
            return typer.prompt(label, default=default)
        return typer.prompt(label)
    if default is not None:
        return default
    raise LzaError(f"{label} is required.")
