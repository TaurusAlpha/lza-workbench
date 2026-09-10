"""Workspace assessment and capability evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from lza_workbench.errors import LzaError
from lza_workbench.installer.config import validate_installer_configuration
from lza_workbench.workspace.schema import WorkspaceConfig, WorkspaceState


class WorkspaceCapability(StrEnum):
    """Independently observable workspace capabilities required by workflows."""

    METADATA_VALID = "metadata_valid"
    CONFIGURATION_PRESENT = "configuration_present"
    INSTALLER_CONFIGURED = "installer_configured"
    INSTALLER_RECORDED_DEPLOYED = "installer_recorded_deployed"
    IMPORTED = "imported"


@dataclass(frozen=True)
class WorkspaceAssessment:
    """Independent facts about the current workspace state."""

    metadata_valid: bool
    configuration_present: bool
    installer_configured: bool
    installer_recorded_deployed: bool
    imported: bool

    def supports(self, capability: WorkspaceCapability) -> bool:
        """Return whether this workspace provides one capability."""
        return {
            WorkspaceCapability.METADATA_VALID: self.metadata_valid,
            WorkspaceCapability.CONFIGURATION_PRESENT: self.configuration_present,
            WorkspaceCapability.INSTALLER_CONFIGURED: self.installer_configured,
            WorkspaceCapability.INSTALLER_RECORDED_DEPLOYED: self.installer_recorded_deployed,
            WorkspaceCapability.IMPORTED: self.imported,
        }[capability]


def evaluate_workspace_assessment(
    workspace_dir: Path,
    config: WorkspaceConfig,
    state: WorkspaceState,
) -> WorkspaceAssessment:
    """Assess independent workspace capabilities from config, filesystem, and state."""
    config_dir = workspace_dir / config.configuration.local_path
    return WorkspaceAssessment(
        metadata_valid=bool((config.customer.slug or "").strip())
        and bool((config.aws.region or "").strip()),
        configuration_present=config_dir.is_dir(),
        installer_configured=validate_installer_configuration(config).is_complete,
        installer_recorded_deployed=bool((state.installer_stack_id or "").strip()),
        imported=state.imported is True,
    )


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
            "(missing installer_stack_id in .lza/state.json). Run 'lza installer deploy' first."
        )


__all__ = [
    "WorkspaceAssessment",
    "WorkspaceCapability",
    "evaluate_workspace_assessment",
    "require_capabilities",
]
