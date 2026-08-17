"""Shared utility functions."""

from __future__ import annotations

import re

import typer

from lza_workbench.errors import LzaError


def normalize_customer_slug(customer_name: str) -> str:
    """Normalize a customer name into a filesystem-safe slug."""
    slug = customer_name.strip().lower()
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"[^a-z0-9-]+", "", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    if not slug:
        raise ValueError("Customer name does not produce a valid workspace slug.")
    return slug


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
