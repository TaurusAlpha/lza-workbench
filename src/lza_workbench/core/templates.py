"""Temporary compatibility alias for configuration templates module (to be removed in Step 16)."""

from __future__ import annotations

from lza_workbench.config.templates import (
    DEFAULT_TEMPLATE_SOURCE,
    OPTIONAL_TEMPLATE_FILES,
    REQUIRED_TEMPLATE_FILES,
    ResolvedTemplateSource,
    resolve_template_source,
    validate_template,
)

__all__ = [
    "DEFAULT_TEMPLATE_SOURCE",
    "OPTIONAL_TEMPLATE_FILES",
    "REQUIRED_TEMPLATE_FILES",
    "ResolvedTemplateSource",
    "resolve_template_source",
    "validate_template",
]
