"""Workspace readiness enforcement and directory structure validation."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from lza_workbench.errors import LzaError
from lza_workbench.workspace.layout.scaffolding import WORKSPACE_MANAGED_PATHS
from lza_workbench.workspace.paths import normalize_path
from lza_workbench.workspace.validation.capabilities import (
    WorkspaceAssessment,
    WorkspaceCapability,
)

if TYPE_CHECKING:
    from lza_workbench.workspace.schema import WorkspaceConfig


def validate_workspace_structure(
    workspace_dir: Path,
    force: bool = False,
) -> bool:
    """Validate an init target and return whether it already exists."""
    target = normalize_path(workspace_dir)
    if not target.exists():
        return False
    if not target.is_dir():
        raise LzaError(f"Target path exists and is not a directory: {target}")
    existing: list[Path] = []
    if not force:
        for path in WORKSPACE_MANAGED_PATHS:
            if (target / path).exists():
                existing.append(target / path)
                raise LzaError(
                    f"Found existing workspace-managed paths: {existing}. "
                    f"To adopt existing workspace, run `lza import {target}` "
                    "or use --force flag to overwrite."
                )
    return True


def require_capabilities(
    assessment: WorkspaceAssessment,
    *required_capabilities: WorkspaceCapability,
    workspace_dir: Path,
    config: WorkspaceConfig,
) -> None:
    """Raise the existing readiness error for the first missing required capability."""
    required = set(required_capabilities)
    if WorkspaceCapability.METADATA_VALID in required and not assessment.metadata_valid:
        raise LzaError(
            f"Workspace at '{workspace_dir}' is missing required core configuration "
            "(AWS authentication/region or customer details in lza-workspace.yaml). "
            "Initialize the workspace with 'lza init' or update lza-workspace.yaml."
        )
    if (
        WorkspaceCapability.CONFIGURATION_PRESENT in required
        and not assessment.configuration_present
    ):
        config_dir = workspace_dir / config.configuration.local_path
        raise LzaError(
            f"Configuration directory '{config_dir}' does not exist or "
            "is missing required LZA templates. Run 'lza init' or 'lza import' first."
        )
    if WorkspaceCapability.INSTALLER_CONFIGURED in required and not assessment.installer_configured:
        raise LzaError(
            "Workspace is missing required installer configuration parameters in "
            "lza-workspace.yaml. Run 'lza installer plan' or update lza-workspace.yaml."
        )
    if (
        WorkspaceCapability.INSTALLER_RECORDED_DEPLOYED in required
        and not assessment.installer_recorded_deployed
    ):
        raise LzaError(
            "Installer CloudFormation stack has not been deployed for this workspace "
            "(missing installer.stack_id in .lza/state.json). Run 'lza installer deploy' first."
        )


__all__ = [
    "require_capabilities",
    "validate_workspace_structure",
]
