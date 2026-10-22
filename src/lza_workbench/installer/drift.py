"""Installer configuration drift and state alignment calculations."""

from __future__ import annotations

from dataclasses import dataclass

from lza_workbench.installer.parameters import build_installer_cfn_parameters
from lza_workbench.installer.schema import LzaInstaller
from lza_workbench.installer.versions import normalize_lza_version
from lza_workbench.workspace.schema import (
    CustomerEnvironmentTarget,
    WorkspaceConfig,
    WorkspaceState,
)


@dataclass(frozen=True)
class StateAlignment:
    """Comparison of recorded installer state with the deployed stack."""

    in_sync: bool


def calculate_configuration_drift(
    config: WorkspaceConfig | None = None,
    deployed_parameters: dict[str, str] | None = None,
    *,
    installer: LzaInstaller | None = None,
    environment_target: CustomerEnvironmentTarget | None = None,
) -> dict[str, tuple[str, str]]:
    """Return deployed and configured values for installer parameters that differ."""
    deployed = deployed_parameters or {}
    configured_parameters = build_installer_cfn_parameters(
        config,
        installer=installer,
        environment_target=environment_target,
    )
    return {
        key: (deployed.get(key, ""), configured_value)
        for key, configured_value in configured_parameters.items()
        if deployed.get(key, "") != configured_value
    }


def calculate_state_alignment(
    state: WorkspaceState,
    *,
    stack_id: str | None,
    stack_status: str | None,
    deployed_version: str | None,
) -> StateAlignment:
    """Compare recorded stack observation with the current stack metadata."""
    obs = state.installer.observation
    if obs is None:
        return StateAlignment(in_sync=False)
    stack_id_matches = obs.stack_id is None or obs.stack_id == stack_id
    stack_status_matches = obs.stack_status == stack_status
    recorded_version = obs.deployed_version or state.installer.template.version
    version_matches = bool(
        deployed_version
        and normalize_lza_version(recorded_version) == normalize_lza_version(deployed_version)
    )
    return StateAlignment(
        in_sync=stack_id_matches and stack_status_matches and version_matches,
    )


def compare_installer_parameters(
    config: WorkspaceConfig | None = None,
    deployed_parameters: dict[str, str] | None = None,
    recorded_parameters: dict[str, str] | None = None,
    *,
    installer: LzaInstaller | None = None,
    environment_target: CustomerEnvironmentTarget | None = None,
) -> str:
    """Classify saved/live differences against the last recorded parameter snapshot."""
    deployed_map = deployed_parameters or {}
    configured = build_installer_cfn_parameters(
        config,
        installer=installer,
        environment_target=environment_target,
    )
    deployed = {key: deployed_map.get(key, "") for key in configured}
    if configured == deployed:
        return "No pending changes"
    if not recorded_parameters or not configured.keys() <= recorded_parameters.keys():
        return "Settings differ"
    recorded = {key: recorded_parameters[key] for key in configured}
    local_changed = configured != recorded
    deployed_changed = deployed != recorded
    if local_changed and deployed_changed:
        return "Both changed"
    return "Saved changes not deployed" if local_changed else "Deployed settings changed"


__all__ = [
    "StateAlignment",
    "calculate_configuration_drift",
    "calculate_state_alignment",
    "compare_installer_parameters",
]
