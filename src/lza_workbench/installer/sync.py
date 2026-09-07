"""Synchronization helpers for reconciling workspace metadata with live AWS installer resources."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from lza_workbench.aws.cloudformation import CfnStackStatusResult
from lza_workbench.errors import LzaError
from lza_workbench.installer.parameters import apply_deployed_installer_parameters
from lza_workbench.installer.templates import INSTALLER_TEMPLATE_FILENAME
from lza_workbench.installer.versions import normalize_lza_version
from lza_workbench.workspace.config import write_workspace_config
from lza_workbench.workspace.schema import WorkspaceConfig, WorkspaceState
from lza_workbench.workspace.state import write_workspace_state


def sync_installer_state(
    *,
    workspace_dir: Path,
    state: WorkspaceState,
    cfn_status: CfnStackStatusResult,
    deployed_version: str | None,
) -> WorkspaceState:
    """Synchronize .lza/state.json deployment metadata with live installer state."""
    if not cfn_status.exists:
        raise LzaError(
            "Cannot synchronize state: CloudFormation installer stack is not deployed "
            "or inaccessible."
        )
    state.installer_stack_id = cfn_status.stack_id
    state.installer_stack_status = cfn_status.stack_status
    if deployed_version is not None:
        state.installer_template_version = deployed_version
    state.updated_at = datetime.now(UTC)
    write_workspace_state(workspace_dir, state)
    return state


def sync_installer_config(
    *,
    workspace_dir: Path,
    config: WorkspaceConfig,
    cfn_status: CfnStackStatusResult,
    deployed_version: str | None,
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
    if deployed_version is not None:
        config.lza.version = normalize_lza_version(deployed_version)
    write_workspace_config(workspace_dir, config)
    return config


def sync_installer_template(
    *,
    workspace_dir: Path,
    config: WorkspaceConfig,
    state: WorkspaceState,
    template_body: str,
) -> Path:
    """Persist the live installer template used by an imported stack."""
    installer_dir = workspace_dir / config.installer.local_path
    template_path = installer_dir / INSTALLER_TEMPLATE_FILENAME
    try:
        installer_dir.mkdir(parents=True, exist_ok=True)
        template_path.write_text(template_body, encoding="utf-8")
    except OSError as exc:
        raise LzaError(
            f"Unable to save imported installer template to {template_path}: {exc}"
        ) from exc

    config.installer.stack_template.source = "local"
    config.installer.stack_template.path = str(template_path.relative_to(workspace_dir))
    config.installer.stack_template.repository = None
    config.installer.stack_template.ref = None
    state.installer_template_digest = sha256(template_body.encode("utf-8")).hexdigest()
    state.installer_downloaded_at = datetime.now(UTC)
    return template_path


__all__ = [
    "sync_installer_config",
    "sync_installer_state",
    "sync_installer_template",
]
