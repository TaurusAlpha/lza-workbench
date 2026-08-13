import json
from pathlib import Path

from pydantic import ValidationError

from lza_workbench.workspace.models import WorkspaceState


def load_workspace_state(path: Path) -> WorkspaceState:
    """Read and validate mutable operational state."""
    if not path.exists():
        return WorkspaceState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return WorkspaceState.model_validate(data)
    except (OSError, json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid workspace state {path}: {exc}") from exc


def write_workspace_state(path: Path, state: WorkspaceState) -> None:
    """Write operational state as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state.model_dump(mode="json"), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
