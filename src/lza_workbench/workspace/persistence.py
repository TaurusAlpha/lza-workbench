"""Workspace persistence: YAML configuration and JSON state loading/saving."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from lza_workbench.errors import LzaError
from lza_workbench.workspace.paths import WORKSPACE_CONFIG_FILE, WORKSPACE_STATE_FILE
from lza_workbench.workspace.schema import WorkspaceConfig, WorkspaceState


def get_config_path(workspace_dir: Path) -> Path:
    """Construct and normalize the absolute configuration file path from workspace root."""
    return workspace_dir.expanduser().resolve() / WORKSPACE_CONFIG_FILE


def get_state_path(workspace_dir: Path) -> Path:
    """Construct absolute operational state path from workspace root."""
    return workspace_dir.expanduser().resolve() / WORKSPACE_STATE_FILE


def load_workspace_config(workspace_dir: Path) -> WorkspaceConfig:
    """Read and validate lza-workspace.yaml from a given workspace directory."""
    path = get_config_path(workspace_dir)
    yaml = YAML()
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.load(handle)
        _reject_persisted_aws_secrets(data)
        return WorkspaceConfig.model_validate(data)
    except (OSError, YAMLError, ValidationError, TypeError, ValueError) as exc:
        raise LzaError(f"Invalid workspace configuration {path}: {exc}") from exc


def write_workspace_config(workspace_dir: Path, config: WorkspaceConfig) -> None:
    """Write validated workspace configuration into the workspace directory as YAML."""
    path = get_config_path(workspace_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    yaml = YAML()
    yaml.default_flow_style = False
    with path.open("w", encoding="utf-8") as handle:
        yaml.dump(config.model_dump(mode="json"), handle)


def load_workspace_state(workspace_dir: Path) -> WorkspaceState:
    """Read and validate mutable operational state from .lza/state.json."""
    path = get_state_path(workspace_dir)
    if not path.exists():
        return WorkspaceState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return WorkspaceState.model_validate(data)
    except (OSError, json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        raise LzaError(f"Invalid workspace state at {path}: {exc}") from exc


def write_workspace_state(workspace_dir: Path, state: WorkspaceState) -> None:
    """Write operational state as JSON into .lza/state.json."""
    path = get_state_path(workspace_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state.model_dump(mode="json"), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def _reject_persisted_aws_secrets(data: object) -> None:
    """Reject workspace configuration that persists AWS secret keys."""
    if not isinstance(data, dict) or not isinstance(aws := data.get("aws"), dict):
        return
    secret_fields = {
        "access_key",
        "secret_access_key",
        "aws_access_key_id",
        "aws_secret_access_key",
    }
    present = sorted(field for field in secret_fields if aws.get(field) is not None)
    if present:
        names = ", ".join(present)
        raise LzaError(
            f"AWS secret field(s) [{names}] are not supported in lza-workspace.yaml. "
            "Remove them and configure credentials externally through an AWS profile, "
            "environment, SSO, or an assumed role."
        )


__all__ = [
    "WORKSPACE_CONFIG_FILE",
    "WORKSPACE_STATE_FILE",
    "get_config_path",
    "get_state_path",
    "load_workspace_config",
    "load_workspace_state",
    "write_workspace_config",
    "write_workspace_state",
]
