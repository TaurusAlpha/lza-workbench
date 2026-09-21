"""Synchronization helpers for reconciling workspace metadata with live AWS installer resources."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from lza_workbench.errors import LzaError
from lza_workbench.infrastructure.aws.cloudformation import CfnStackStatusResult
from lza_workbench.installer.parameters import apply_deployed_installer_parameters
from lza_workbench.installer.templates import INSTALLER_TEMPLATE_FILENAME
from lza_workbench.installer.versions import normalize_lza_version
from lza_workbench.workspace.persistence import write_workspace_config, write_workspace_state
from lza_workbench.workspace.schema import WorkspaceConfig, WorkspaceState


def apply_installer_state_sync(
    *,
    state: WorkspaceState,
    cfn_status: CfnStackStatusResult,
    deployed_version: str | None,
) -> WorkspaceState:
    """Apply discovered installer state without persisting it."""
    if not cfn_status.exists:
        raise LzaError(
            "Cannot synchronize state: CloudFormation installer stack is not deployed "
            "or inaccessible."
        )
    state.installer.stack_id = cfn_status.stack_id
    state.installer.stack_status = cfn_status.stack_status
    if cfn_status.deployed_parameters:
        state.installer.deployed_parameters = dict(cfn_status.deployed_parameters)
    if deployed_version is not None:
        state.installer.template_version = deployed_version
    state.updated_at = datetime.now(UTC)
    return state


def sync_installer_state(
    *,
    workspace_dir: Path,
    state: WorkspaceState,
    cfn_status: CfnStackStatusResult,
    deployed_version: str | None,
) -> WorkspaceState:
    """Synchronize .lza/state.json deployment metadata with live installer state."""
    apply_installer_state_sync(
        state=state,
        cfn_status=cfn_status,
        deployed_version=deployed_version,
    )
    write_workspace_state(workspace_dir, state)
    return state


def apply_installer_config_sync(
    *,
    config: WorkspaceConfig,
    cfn_status: CfnStackStatusResult,
    deployed_version: str | None,
) -> WorkspaceConfig:
    """Apply discovered installer configuration without persisting it."""
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
    if deployed_version is not None:
        config.lza.version = normalize_lza_version(deployed_version)
    return config


def sync_installer_config(
    *,
    workspace_dir: Path,
    config: WorkspaceConfig,
    cfn_status: CfnStackStatusResult,
    deployed_version: str | None,
) -> WorkspaceConfig:
    """Synchronize lza-workspace.yaml with deployed installer parameters."""
    apply_installer_config_sync(
        config=config,
        cfn_status=cfn_status,
        deployed_version=deployed_version,
    )
    write_workspace_config(workspace_dir, config)
    return config


def prepare_installer_template_sync(
    *,
    workspace_dir: Path,
    config: WorkspaceConfig,
    state: WorkspaceState,
    template_body: str,
) -> Path:
    """Apply imported template metadata and return its intended workspace path."""
    installer_dir = workspace_dir / config.installer.local_path
    template_path = installer_dir / INSTALLER_TEMPLATE_FILENAME
    config.installer.stack_template.source = "local"
    config.installer.stack_template.path = str(template_path.relative_to(workspace_dir))
    config.installer.stack_template.repository = None
    config.installer.stack_template.ref = None
    state.installer.template_digest = sha256(template_body.encode("utf-8")).hexdigest()
    state.installer.downloaded_at = datetime.now(UTC)
    return template_path


def write_installer_template(*, template_path: Path, template_body: str) -> None:
    try:
        template_path.parent.mkdir(parents=True, exist_ok=True)
        template_path.write_text(template_body, encoding="utf-8")
    except OSError as exc:
        raise LzaError(
            f"Unable to save imported installer template to {template_path}: {exc}"
        ) from exc


def sync_installer_template(
    *,
    workspace_dir: Path,
    config: WorkspaceConfig,
    state: WorkspaceState,
    template_body: str,
) -> Path:
    template_path = prepare_installer_template_sync(
        workspace_dir=workspace_dir,
        config=config,
        state=state,
        template_body=template_body,
    )
    write_installer_template(template_path=template_path, template_body=template_body)
    return template_path


__all__ = [
    "apply_installer_config_sync",
    "apply_installer_state_sync",
    "prepare_installer_template_sync",
    "sync_installer_config",
    "sync_installer_state",
    "sync_installer_template",
    "write_installer_template",
]
