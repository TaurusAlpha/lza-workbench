"""Pure calculations used by installer status reporting."""

from __future__ import annotations

from dataclasses import dataclass

from lza_workbench.installer.parameters import build_installer_cfn_parameters
from lza_workbench.installer.versions import normalize_lza_version
from lza_workbench.workspace.models import WorkspaceConfig, WorkspaceState


@dataclass(frozen=True)
class StateAlignment:
    """Comparison of recorded installer state with the deployed stack."""

    in_sync: bool


def calculate_configuration_drift(
    config: WorkspaceConfig, deployed_parameters: dict[str, str]
) -> dict[str, tuple[str, str]]:
    """Return deployed and configured values for installer parameters that differ."""
    configured_parameters = build_installer_cfn_parameters(config)
    return {
        key: (deployed_parameters.get(key, ""), configured_value)
        for key, configured_value in configured_parameters.items()
        if deployed_parameters.get(key, "") != configured_value
    }


def calculate_state_alignment(
    state: WorkspaceState,
    *,
    stack_id: str | None,
    stack_status: str | None,
    deployed_version: str,
) -> StateAlignment:
    """Compare recorded deployment metadata with the current stack metadata."""
    stack_id_matches = state.installer_stack_id is None or state.installer_stack_id == stack_id
    stack_status_matches = state.installer_stack_status == stack_status
    version_matches = normalize_lza_version(
        state.installer_template_version
    ) == normalize_lza_version(deployed_version)
    return StateAlignment(
        in_sync=stack_id_matches and stack_status_matches and version_matches,
    )
