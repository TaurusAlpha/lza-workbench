"""Compatibility wrapper for workspace import command (to be removed in Step 16)."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.cli.commands.workspace_import import (
    render_workspace_import_result,
    workspace_import_command,
)
from lza_workbench.workflows.workspace_import import (
    ExistingMetadata,
    WorkspaceImportResult,
    build_import_workspace_config,
    import_workspace_workflow,
    load_existing_metadata,
    resolve_import_paths,
)


def build_workspace_config(*args, **kwargs):
    return build_import_workspace_config(*args, **kwargs)


def run_import(
    *,
    customer_name: str | None = None,
    workspace_dir: Path,
    config_dir: Path | None = None,
    aws_auth_type: str = "profile",
    aws_profile: str | None = None,
    aws_region: str | None = None,
    lza_version: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    skip_aws_check: bool = False,
    interactive: bool = False,
) -> None:
    """Create or update generated metadata without changing LZA configuration files."""
    workspace_import_command(
        workspace_dir=workspace_dir,
        customer_name=customer_name,
        config_dir=config_dir,
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
    "ExistingMetadata",
    "WorkspaceImportResult",
    "build_import_workspace_config",
    "build_workspace_config",
    "import_workspace_workflow",
    "load_existing_metadata",
    "render_workspace_import_result",
    "resolve_import_paths",
    "run_import",
    "workspace_import_command",
]
