"""Active workspace state for the local Web interface."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from lza_workbench.errors import LzaError
from lza_workbench.workspace.import_workspace import ImportWorkspacePreparation


class ActiveWorkspaceContext:
    """Manage the active workspace and in-flight Web operations."""

    def __init__(self, workspace_dir: Path | None = None, dev_mode: bool = False) -> None:
        self.workspace_dir: Path | None = workspace_dir.resolve() if workspace_dir else None
        self.prepared_import: ImportWorkspacePreparation | None = None
        self.dev_mode: bool = dev_mode
        self._cache: dict[str, tuple[float, Any]] = {}

    def set_workspace_dir(self, workspace_dir: Path) -> None:
        self.workspace_dir = workspace_dir.resolve()
        self.prepared_import = None
        self.clear_cache()

    def require_workspace_dir(self) -> Path:
        if self.workspace_dir is None:
            raise LzaError("No active workspace is open. Please open or create a workspace.")
        return self.workspace_dir

    def get_cached(self, key: str, ttl: float = 30.0) -> Any | None:
        if key in self._cache:
            cached_at, value = self._cache[key]
            if time.monotonic() - cached_at < ttl:
                return value
            del self._cache[key]
        return None

    def set_cached(self, key: str, value: Any) -> None:
        self._cache[key] = (time.monotonic(), value)

    def clear_cache(self) -> None:
        self._cache.clear()
