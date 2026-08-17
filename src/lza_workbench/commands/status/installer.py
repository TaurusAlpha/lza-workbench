"""Compatibility wrapper for installer status command (to be removed in Step 16)."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.aws.cloudformation import get_cloudformation_stack_status
from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.cli.commands.status_installer import (
    render_installer_status,
    status_installer_command,
)
from lza_workbench.workflows.status_installer import (
    InstallerStatusResult,
    get_installer_status_workflow,
    prepare_installer_status,
    sync_installer_config,
    sync_installer_state,
)
from lza_workbench.workspace.context import load_workspace_context


def run_installer_status(
    *, sync_state: bool = False, sync_config: bool = False, target_dir: Path | None = None
) -> None:
    """Query AWS, optionally synchronize, then render an installer status result."""
    status_installer_command(
        sync_state=sync_state,
        sync_config=sync_config,
        target_dir=target_dir,
    )


__all__ = [
    "InstallerStatusResult",
    "get_cloudformation_stack_status",
    "get_installer_status_workflow",
    "load_workspace_context",
    "prepare_installer_status",
    "render_installer_status",
    "resolve_aws_execution_context",
    "run_installer_status",
    "status_installer_command",
    "sync_installer_config",
    "sync_installer_state",
]
