import json
from pathlib import Path

from pydantic import ValidationError

from lza_workbench.workspace.models import WorkspaceState

WORKSPACE_STATE_FILE = Path(".lza") / "state.json"


def _get_state_path(workspace_dir: Path) -> Path:
    """Construct absolute operational state path from workspace root."""
    return workspace_dir.expanduser().resolve() / WORKSPACE_STATE_FILE


def load_workspace_state(workspace_dir: Path) -> WorkspaceState:
    """Read and validate mutable operational state from .lza/state.json."""
    path = _get_state_path(workspace_dir)
    if not path.exists():
        return WorkspaceState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return WorkspaceState.model_validate(data)
    except (OSError, json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid workspace state at {path}: {exc}") from exc


def write_workspace_state(workspace_dir: Path, state: WorkspaceState) -> None:
    """Write operational state as JSON into .lza/state.json."""
    path = _get_state_path(workspace_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state.model_dump(mode="json"), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
