from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

from lza_workbench.errors import LzaError
from lza_workbench.installer.config import validate_installer_configuration
from lza_workbench.workspace.config import load_workspace_config
from lza_workbench.workspace.models import WorkspaceConfig, WorkspaceState
from lza_workbench.workspace.paths import resolve_workspace_dir
from lza_workbench.workspace.state import load_workspace_state


class WorkspaceReadinessLevel(IntEnum):
    """Progressive readiness levels of an LZA Workbench workspace."""

    UNINITIALIZED = 0
    CORE_CONFIGURED = 1
    IMPORTED = 2
    CONFIGURED = 3
    DEPLOYED = 4


@dataclass(frozen=True)
class WorkspaceContext:
    """Immutable runtime context containing resolved workspace information."""

    workspace_dir: Path
    config: WorkspaceConfig
    state: WorkspaceState
    readiness_level: WorkspaceReadinessLevel


def evaluate_workspace_readiness(
    workspace_dir: Path,
    config: WorkspaceConfig,
    state: WorkspaceState,
) -> WorkspaceReadinessLevel:
    """Evaluate current workspace readiness level based on config, directory, and state."""
    if not (config.customer.slug or "").strip() or not (config.aws.region or "").strip():
        return WorkspaceReadinessLevel.UNINITIALIZED

    config_dir = workspace_dir / config.configuration.local_path
    if not config_dir.is_dir():
        return WorkspaceReadinessLevel.CORE_CONFIGURED

    if not validate_installer_configuration(config).is_complete:
        return WorkspaceReadinessLevel.IMPORTED

    if (state.installer_stack_id or "").strip():
        return WorkspaceReadinessLevel.DEPLOYED

    return WorkspaceReadinessLevel.CONFIGURED


def load_workspace_context(
    target_dir: Path | None = None,
    min_readiness: WorkspaceReadinessLevel = WorkspaceReadinessLevel.CORE_CONFIGURED,
) -> WorkspaceContext:
    """Resolve workspace directory, load configuration and state, and enforce readiness level."""
    workspace_dir = resolve_workspace_dir(target_dir)
    config = load_workspace_config(workspace_dir)
    state = load_workspace_state(workspace_dir)

    readiness = evaluate_workspace_readiness(workspace_dir, config, state)

    if readiness < min_readiness:
        _raise_readiness_error(readiness, min_readiness, workspace_dir, config)

    return WorkspaceContext(
        workspace_dir=workspace_dir,
        config=config,
        state=state,
        readiness_level=readiness,
    )


def _raise_readiness_error(
    current: WorkspaceReadinessLevel,
    required: WorkspaceReadinessLevel,
    workspace_dir: Path,
    config: WorkspaceConfig,
) -> None:
    """Format and raise user-friendly error when minimum readiness level is not satisfied."""
    if current == WorkspaceReadinessLevel.UNINITIALIZED:
        raise LzaError(
            f"Workspace at '{workspace_dir}' is missing required core configuration "
            "(AWS authentication/region or customer details in lza-workspace.yaml). "
            "Initialize the workspace with 'lza init' or update lza-workspace.yaml."
        )
    if current == WorkspaceReadinessLevel.CORE_CONFIGURED:
        config_dir = workspace_dir / config.configuration.local_path
        raise LzaError(
            f"Configuration directory '{config_dir}' does not exist or "
            "is missing required LZA templates. Run 'lza init' or 'lza import' first."
        )
    if current == WorkspaceReadinessLevel.IMPORTED:
        raise LzaError(
            "Workspace is missing required installer configuration parameters in "
            "lza-workspace.yaml. Run 'lza installer plan' or update lza-workspace.yaml."
        )
    if (
        current == WorkspaceReadinessLevel.CONFIGURED
        and required == WorkspaceReadinessLevel.DEPLOYED
    ):
        raise LzaError(
            "Installer CloudFormation stack has not been deployed for this workspace "
            "(missing installer_stack_id in .lza/state.json). Run 'lza installer deploy' first."
        )
    raise LzaError(
        f"Workspace readiness level '{current.name}' does not meet "
        f"required level '{required.name}'."
    )
