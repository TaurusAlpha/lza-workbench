"""Compatibility re-exports for utility functions (to be removed in Step 16)."""

from __future__ import annotations

from lza_workbench.cli.presentation import value_or_prompt
from lza_workbench.workspace.paths import normalize_customer_slug

__all__ = ["normalize_customer_slug", "value_or_prompt"]
