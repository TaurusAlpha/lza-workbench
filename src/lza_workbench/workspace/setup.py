"""Setup helpers for workspace directory structure and files."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.errors import LzaError
from lza_workbench.workspace.config import WORKSPACE_CONFIG_FILE, write_workspace_config
from lza_workbench.workspace.paths import normalize_path
from lza_workbench.workspace.schema import WorkspaceConfig, WorkspaceState
from lza_workbench.workspace.state import WORKSPACE_STATE_FILE, write_workspace_state

WORKSPACE_MANAGED_PATHS = [
    Path(".lza"),
    Path("aws-accelerator-config"),
    Path("aws-accelerator-installer"),
    WORKSPACE_CONFIG_FILE,
    WORKSPACE_STATE_FILE,
]


def validate_workspace_structure(
    workspace_dir: Path,
    force: bool = False,
) -> bool:
    """Validate an init target and return whether it already exists."""
    target = normalize_path(workspace_dir)
    if not target.exists():
        return False
    if not target.is_dir():
        raise LzaError(f"Target path exists and is not a directory: {target}")
    existing: list[Path] = []
    if not force:
        for path in WORKSPACE_MANAGED_PATHS:
            if (target / path).exists():
                existing.append(target / path)
                raise LzaError(
                    f"Found existing workspace-managed paths: {existing}. "
                    f"To adopt existing workspace, run `lza import {target}` "
                    "or use --force flag to overwrite."
                )
    return True


def create_workspace(
    *,
    workspace_dir: Path,
    config: WorkspaceConfig,
    state: WorkspaceState,
) -> None:
    """Create or reinitialize generated workspace files."""
    target = normalize_path(workspace_dir)
    target.mkdir(parents=True, exist_ok=True)
    (target / ".lza" / "logs").mkdir(parents=True, exist_ok=True)
    (target / config.installer.local_path).mkdir(parents=True, exist_ok=True)

    write_workspace_config(target, config)
    write_workspace_state(target, state)


def overwrite_workspace_metadata(
    workspace_dir: Path, config: WorkspaceConfig, state: WorkspaceState
) -> None:
    """Replace generated metadata without changing customer-owned configuration files."""
    target = normalize_path(workspace_dir)
    write_workspace_config(target, config)
    write_workspace_state(target, state)


def planned_write_paths(workspace_dir: Path, config: WorkspaceConfig) -> list[Path]:
    """Return the paths workspace initialization will create or replace."""
    return [
        workspace_dir,
        workspace_dir / WORKSPACE_CONFIG_FILE,
        workspace_dir / config.installer.local_path,
        workspace_dir / WORKSPACE_STATE_FILE,
        workspace_dir / ".lza" / "logs",
    ]
