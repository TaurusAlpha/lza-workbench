"""Workflow alias for local LZA configuration synchronization."""

from __future__ import annotations

from lza_workbench.workflows.config_push import (
    ConfigPushResult,
    ConfigUploadResult,
    push_configuration_workflow,
)

upload_configuration_workflow = push_configuration_workflow

__all__ = [
    "ConfigPushResult",
    "ConfigUploadResult",
    "push_configuration_workflow",
    "upload_configuration_workflow",
]

