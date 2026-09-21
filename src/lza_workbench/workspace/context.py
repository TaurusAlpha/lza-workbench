"""Workspace execution context."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lza_workbench.workspace.paths import resolve_workspace_dir
from lza_workbench.workspace.persistence import (
    WORKSPACE_CONFIG_FILE,
    WORKSPACE_STATE_FILE,
    load_workspace_config,
    load_workspace_state,
)
from lza_workbench.workspace.schema import WorkspaceConfig, WorkspaceState
from lza_workbench.workspace.validation import (
    WorkspaceAssessment,
    WorkspaceCapability,
    evaluate_workspace_assessment,
    require_capabilities,
)


@dataclass(frozen=True)
class WorkspaceContext:
    """Immutable runtime context containing resolved workspace information."""

    workspace_dir: Path
    config: WorkspaceConfig
    state: WorkspaceState
    assessment: WorkspaceAssessment

    @property
    def config_dir(self) -> Path:
        return self.workspace_dir / self.config.configuration.local_path

    @property
    def installer_dir(self) -> Path:
        return self.workspace_dir / self.config.installer.local_path

    @property
    def state_dir(self) -> Path:
        return self.workspace_dir / ".lza"

    @property
    def config_file(self) -> Path:
        return self.workspace_dir / WORKSPACE_CONFIG_FILE

    @property
    def state_file(self) -> Path:
        return self.workspace_dir / WORKSPACE_STATE_FILE


def load_workspace_context(
    target_dir: Path | None = None,
    required_capabilities: tuple[WorkspaceCapability, ...] = (WorkspaceCapability.METADATA_VALID,),
) -> WorkspaceContext:
    """Resolve workspace information and enforce the requested capabilities."""
    workspace_dir = resolve_workspace_dir(target_dir)
    config = load_workspace_config(workspace_dir)
    state = load_workspace_state(workspace_dir)

    assessment = evaluate_workspace_assessment(workspace_dir, config, state)
    require_capabilities(
        assessment,
        *required_capabilities,
        workspace_dir=workspace_dir,
        config=config,
    )

    return WorkspaceContext(
        workspace_dir=workspace_dir,
        config=config,
        state=state,
        assessment=assessment,
    )


__all__ = [
    "WorkspaceAssessment",
    "WorkspaceCapability",
    "WorkspaceContext",
    "evaluate_workspace_assessment",
    "load_workspace_context",
    "require_capabilities",
]
