"""Filesystem layout, directory scaffolding, and managed paths."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from lza_workbench.workspace.paths import (
    WORKSPACE_CONFIG_FILE,
    WORKSPACE_STATE_FILE,
    normalize_path,
)

if TYPE_CHECKING:
    from lza_workbench.workspace.schema import (
        WorkspaceConfig,
        WorkspaceState,
    )

WORKSPACE_MANAGED_PATHS = [
    Path(".lza"),
    Path("aws-accelerator-config"),
    Path("aws-accelerator-installer"),
    WORKSPACE_CONFIG_FILE,
    WORKSPACE_STATE_FILE,
]


def create_workspace(
    *,
    workspace_dir: Path,
    config: WorkspaceConfig,
    state: WorkspaceState,
) -> None:
    """Create or reinitialize generated workspace files."""
    from lza_workbench.workspace.persistence import write_workspace_config, write_workspace_state

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
    from lza_workbench.workspace.persistence import write_workspace_config, write_workspace_state

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


__all__ = [
    "WORKSPACE_MANAGED_PATHS",
    "create_workspace",
    "overwrite_workspace_metadata",
    "planned_write_paths",
]
