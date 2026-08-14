import shutil
from pathlib import Path

from lza_workbench.core.errors import LzaError
from lza_workbench.workspace.config import WORKSPACE_CONFIG_FILE, write_workspace_config
from lza_workbench.workspace.models import WorkspaceConfig, WorkspaceState
from lza_workbench.workspace.paths import normalize_path
from lza_workbench.workspace.state import WORKSPACE_STATE_FILE, write_workspace_state


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
    if not force:
        raise LzaError(
            f"Workspace directory already exists: {target}. To adopt it, run `lza import {target}`."
        )
    return True


def create_workspace(
    *,
    workspace_dir: Path,
    template_config_dir: Path,
    config: WorkspaceConfig,
    state: WorkspaceState,
) -> None:
    """Create or reinitialize generated workspace files."""
    target = normalize_path(workspace_dir)
    target.mkdir(parents=True, exist_ok=True)
    (target / ".lza" / "logs").mkdir(parents=True, exist_ok=True)
    (target / config.installer.local_path).mkdir(parents=True, exist_ok=True)

    shutil.copytree(
        template_config_dir, target / config.configuration.local_path, dirs_exist_ok=True
    )

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
    """Return the paths initialization will create or replace."""
    return [
        workspace_dir,
        workspace_dir / WORKSPACE_CONFIG_FILE,
        workspace_dir / config.configuration.local_path,
        workspace_dir / config.installer.local_path,
        workspace_dir / WORKSPACE_STATE_FILE,
        workspace_dir / ".lza" / "logs",
    ]
