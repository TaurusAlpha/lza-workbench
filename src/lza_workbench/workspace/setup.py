import re
import shutil
from pathlib import Path

from lza_workbench.core.errors import LzaError
from lza_workbench.utils.helpers import normalize_path
from lza_workbench.workspace.config import WORKSPACE_CONFIG_FILE, write_workspace_config
from lza_workbench.workspace.models import WorkspaceConfig, WorkspaceState
from lza_workbench.workspace.state import WORKSPACE_STATE_FILE, write_workspace_state


def normalize_customer_slug(customer_name: str) -> str:
    """Normalize a customer name into a filesystem-safe slug."""
    slug = customer_name.strip().lower()
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"[^a-z0-9-]+", "", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    if not slug:
        raise ValueError("Customer name does not produce a valid workspace slug.")
    return slug


def is_workspace_dir(path: Path) -> bool:
    """Return whether a directory declares itself as a workspace."""
    return (normalize_path(path) / WORKSPACE_CONFIG_FILE).is_file()


def resolve_workspace_dir(target_dir: Path | None = None) -> Path:
    """Resolve workspace directory containing lza-workspace.yaml starting from cwd or target_dir."""
    current = normalize_path(target_dir or Path.cwd())
    for directory in [current, *current.parents]:
        if is_workspace_dir(directory):
            return directory
    raise LzaError(
        f"Command must be run inside an LZA workspace directory (missing {WORKSPACE_CONFIG_FILE})."
    )


def resolve_init_workspace_dir(customer_name: str, workspace_dir: Path | None = None) -> Path:
    """Resolve an explicit init target or the default customer workspace path."""
    if workspace_dir is not None:
        return normalize_path(workspace_dir)
    return normalize_path(Path.cwd() / normalize_customer_slug(customer_name))


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
            f"Workspace directory already exists: {target}. "
            f"To adopt it, run `lza import {target}`."
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
