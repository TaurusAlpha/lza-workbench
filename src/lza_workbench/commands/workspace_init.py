"""Compatibility wrapper for workspace init command (to be removed in Step 16)."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.cli.commands.workspace_init import (
    render_workspace_init_result,
    workspace_init_command,
)
from lza_workbench.workflows.workspace_init import (
    WorkspaceInitResult,
    build_workspace_config,
    init_workspace_workflow,
    resolve_packaged_template,
)


def run_init(
    *,
    customer_name: str,
    workspace_dir: Path | None = None,
    aws_auth_type: str = "profile",
    aws_profile: str | None = None,
    aws_region: str | None = None,
    lza_version: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    skip_aws_check: bool = True,
    interactive: bool = False,
) -> None:
    """Create a customer workspace using the configured packaged template."""
    workspace_init_command(
        customer_name=customer_name,
        workspace_dir=workspace_dir,
        aws_auth_type=aws_auth_type,
        aws_profile=aws_profile or "",
        aws_region=aws_region or "",
        lza_version=lza_version,
        dry_run=dry_run,
        force=force,
        skip_aws_check=skip_aws_check,
        interactive=interactive,
    )


__all__ = [
    "WorkspaceInitResult",
    "build_workspace_config",
    "init_workspace_workflow",
    "render_workspace_init_result",
    "resolve_packaged_template",
    "run_init",
    "workspace_init_command",
]
