"""Active workspace state for the local Web interface."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.errors import LzaError
from lza_workbench.workspace.import_workspace import ImportWorkspacePreparation


class ActiveWorkspaceContext:
    """Manage the active workspace and in-flight Web operations."""

    def __init__(self, workspace_dir: Path | None = None) -> None:
        self.workspace_dir: Path | None = workspace_dir.resolve() if workspace_dir else None
        self.prepared_import: ImportWorkspacePreparation | None = None

    def set_workspace_dir(self, workspace_dir: Path) -> None:
        self.workspace_dir = workspace_dir.resolve()
        self.prepared_import = None

    def require_workspace_dir(self) -> Path:
        if self.workspace_dir is None:
            raise LzaError("No active workspace is open. Please open or create a workspace.")
        return self.workspace_dir
