"""Shared CLI input, prompting, and parameter resolution utilities."""

from __future__ import annotations

import typer

from lza_workbench.errors import LzaError


def value_or_prompt(
    label: str,
    value: str | None,
    default: str | None = None,
    interactive: bool = True,
) -> str:
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


__all__ = ["value_or_prompt"]
