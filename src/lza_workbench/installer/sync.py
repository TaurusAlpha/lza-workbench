"""Synchronization helpers for reconciling workspace metadata with live AWS installer resources."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lza_workbench.aws.cloudformation import CfnStackStatusResult
from lza_workbench.errors import LzaError
from lza_workbench.installer.parameters import apply_deployed_installer_parameters
from lza_workbench.workspace.config import write_workspace_config
from lza_workbench.workspace.schema import WorkspaceConfig, WorkspaceState
from lza_workbench.workspace.state import write_workspace_state


def sync_installer_state(
    *,
    workspace_dir: Path,
    state: WorkspaceState,
    cfn_status: CfnStackStatusResult,
    deployed_version: str,
) -> WorkspaceState:
    """Synchronize .lza/state.json deployment metadata with live installer state."""
    if not cfn_status.exists:
        raise LzaError(
            "Cannot synchronize state: CloudFormation installer stack is not deployed "
            "or inaccessible."
        )
    state.installer_stack_id = cfn_status.stack_id
    state.installer_stack_status = cfn_status.stack_status
    state.installer_template_version = deployed_version
    state.updated_at = datetime.now(UTC)
    write_workspace_state(workspace_dir, state)
    return state


def sync_installer_config(
    *,
    workspace_dir: Path,
    config: WorkspaceConfig,
    cfn_status: CfnStackStatusResult,
) -> WorkspaceConfig:
    """Synchronize lza-workspace.yaml with deployed installer parameters."""
    if not cfn_status.exists or not cfn_status.deployed_parameters:
        raise LzaError(
            "Cannot synchronize config: CloudFormation installer stack is not deployed "
            "or has no parameters."
        )
    apply_deployed_installer_parameters(
        config,
        cfn_status.deployed_parameters,
        stack_id=cfn_status.stack_id,
    )
    write_workspace_config(workspace_dir, config)
    return config


__all__ = [
    "sync_installer_config",
    "sync_installer_state",
]
