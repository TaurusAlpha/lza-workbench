"""Workspace persistence: YAML configuration and atomic JSON state loading/saving."""

from __future__ import annotations

import fcntl
import io
import json
import os
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from lza_workbench.errors import LzaError
from lza_workbench.workspace.paths import WORKSPACE_CONFIG_FILE, WORKSPACE_STATE_FILE
from lza_workbench.workspace.schema import WorkspaceConfig, WorkspaceState


def get_config_path(workspace_dir: Path) -> Path:
    return workspace_dir.expanduser().resolve() / WORKSPACE_CONFIG_FILE


def get_state_path(workspace_dir: Path) -> Path:
    return workspace_dir.expanduser().resolve() / WORKSPACE_STATE_FILE


def atomic_write_text(path: Path, content: str) -> None:
    """Atomically write UTF-8 text to a file via a sibling temporary file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


@contextmanager
def state_file_lock(state_path: Path) -> Iterator[None]:
    """Acquire an exclusive advisory lock around workspace state file mutations."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = state_path.parent / ".state.lock"
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def load_workspace_config(workspace_dir: Path) -> WorkspaceConfig:
    path = get_config_path(workspace_dir)
    yaml = YAML()
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.load(handle)
        _assert_no_persisted_aws_secrets(data)
        return WorkspaceConfig.model_validate(data)
    except (OSError, YAMLError, ValidationError, TypeError, ValueError) as exc:
        raise LzaError(f"Invalid workspace configuration {path}: {exc}") from exc


def write_workspace_config(workspace_dir: Path, config: WorkspaceConfig) -> None:
    path = get_config_path(workspace_dir)
    yaml = YAML()
    yaml.default_flow_style = False
    buffer = io.StringIO()
    yaml.dump(config.model_dump(mode="json"), buffer)
    atomic_write_text(path, buffer.getvalue())


def load_workspace_state(workspace_dir: Path) -> WorkspaceState:
    path = get_state_path(workspace_dir)
    if not path.exists():
        return WorkspaceState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return WorkspaceState.model_validate(data)
    except (OSError, json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        raise LzaError(f"Invalid workspace state at {path}: {exc}") from exc


def write_workspace_state(workspace_dir: Path, state: WorkspaceState) -> None:
    path = get_state_path(workspace_dir)
    serialized = json.dumps(state.model_dump(mode="json"), indent=2, sort_keys=False) + "\n"
    with state_file_lock(path):
        atomic_write_text(path, serialized)


def update_workspace_state(
    workspace_dir: Path,
    mutator: Callable[[WorkspaceState], None],
) -> WorkspaceState:
    """Atomically load, mutate, and write .lza/state.json under an exclusive file lock."""
    path = get_state_path(workspace_dir)
    with state_file_lock(path):
        state = load_workspace_state(workspace_dir)
        mutator(state)
        serialized = json.dumps(state.model_dump(mode="json"), indent=2, sort_keys=False) + "\n"
        atomic_write_text(path, serialized)
        return state


def _assert_no_persisted_aws_secrets(raw_config: object) -> None:
    """Reject workspace configuration that persists AWS secret keys."""
    if not isinstance(raw_config, dict) or not isinstance(aws := raw_config.get("aws"), dict):
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
    "atomic_write_text",
    "get_config_path",
    "get_state_path",
    "load_workspace_config",
    "load_workspace_state",
    "state_file_lock",
    "update_workspace_state",
    "write_workspace_config",
    "write_workspace_state",
]
