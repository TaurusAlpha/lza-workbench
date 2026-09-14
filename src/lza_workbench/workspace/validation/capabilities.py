"""Workspace capability enumeration and evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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
    from lza_workbench.installer.validation.config import validate_installer_configuration

    config_dir = workspace_dir / config.configuration.local_path
    return WorkspaceAssessment(
        metadata_valid=bool((config.customer.slug or "").strip())
        and bool((config.aws.region or "").strip()),
        configuration_present=config_dir.is_dir(),
        installer_configured=validate_installer_configuration(config).is_complete,
        installer_recorded_deployed=bool((state.installer.stack_id or "").strip()),
        imported=state.imported is True,
    )


__all__ = [
    "WorkspaceAssessment",
    "WorkspaceCapability",
    "evaluate_workspace_assessment",
]
