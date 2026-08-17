"""Pure workspace naming and path-discovery helpers."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.errors import LzaError
from lza_workbench.utils.helpers import normalize_customer_slug
from lza_workbench.workspace.config import WORKSPACE_CONFIG_FILE


def normalize_path(path: Path) -> Path:
    """Consistently expand user home directory and resolve path."""
    return path.expanduser().resolve()


def is_workspace_dir(path: Path) -> bool:
    """Return whether a directory declares itself as a workspace."""
    return (normalize_path(path) / WORKSPACE_CONFIG_FILE).is_file()


def resolve_workspace_dir(target_dir: Path | None = None) -> Path:
    """Find the workspace directory at or above a target path."""
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
