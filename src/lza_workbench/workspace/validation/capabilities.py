"""Workspace capability enumeration and evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lza_workbench.workspace.schema import WorkspaceConfig


class WorkspaceCapability(StrEnum):
    """Independently observable local workspace capabilities required by workflows."""

    METADATA_VALID = "metadata_valid"
    CONFIGURATION_PRESENT = "configuration_present"
    INSTALLER_CONFIGURED = "installer_configured"


@dataclass(frozen=True)
class WorkspaceAssessment:
    """Independent facts about local workspace structure and configuration."""

    metadata_valid: bool
    configuration_present: bool
    installer_configured: bool

    def supports(self, capability: WorkspaceCapability) -> bool:
        """Return whether this workspace provides one capability."""
        return {
            WorkspaceCapability.METADATA_VALID: self.metadata_valid,
            WorkspaceCapability.CONFIGURATION_PRESENT: self.configuration_present,
            WorkspaceCapability.INSTALLER_CONFIGURED: self.installer_configured,
        }[capability]


def evaluate_workspace_assessment(
    workspace_dir: Path,
    config: WorkspaceConfig,
) -> WorkspaceAssessment:
    """Assess local workspace structural and configuration readiness without runtime state."""
    from lza_workbench.installer.validation.config import validate_installer_configuration

    config_dir = workspace_dir / config.configuration.local_path
    return WorkspaceAssessment(
        metadata_valid=bool((config.customer.slug or "").strip())
        and bool((config.aws.region or "").strip()),
        configuration_present=config_dir.is_dir(),
        installer_configured=validate_installer_configuration(config).is_complete,
    )


__all__ = [
    "WorkspaceAssessment",
    "WorkspaceCapability",
    "evaluate_workspace_assessment",
]
