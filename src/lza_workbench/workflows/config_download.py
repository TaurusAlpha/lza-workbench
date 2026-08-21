"""Workflow for downloading and extracting LZA configuration archives (alias for pull)."""

from __future__ import annotations

from lza_workbench.workflows.config_pull import (
    ConfigDownloadResult,
    ConfigPullResult,
    pull_configuration_workflow,
)

download_configuration_workflow = pull_configuration_workflow

__all__ = [
    "ConfigDownloadResult",
    "ConfigPullResult",
    "download_configuration_workflow",
    "pull_configuration_workflow",
]

