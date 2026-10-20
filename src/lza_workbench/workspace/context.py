"""Local workspace boundary and context resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lza_workbench.workspace.paths import resolve_workspace_dir
from lza_workbench.workspace.persistence import (
    WORKSPACE_CONFIG_FILE,
    WORKSPACE_STATE_FILE,
    load_workspace_config,
    load_workspace_state,
)
from lza_workbench.workspace.schema import (
    CustomerEnvironmentTarget,
    WorkspaceConfig,
    WorkspaceState,
)
from lza_workbench.workspace.validation import (
    WorkspaceAssessment,
    WorkspaceCapability,
    evaluate_workspace_assessment,
    require_capabilities,
)


@dataclass(frozen=True)
class WorkspaceContext:
    """Immutable local workspace context containing resolved paths, configuration, and readiness."""

    workspace_dir: Path
    config: WorkspaceConfig
    state: WorkspaceState = field(default_factory=WorkspaceState)
    assessment: WorkspaceAssessment | None = None

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

    @property
    def environment_target(self) -> CustomerEnvironmentTarget:
        return self.config.environment_target


def load_workspace_context(
    target_dir: Path | None = None,
    required_capabilities: tuple[WorkspaceCapability, ...] = (WorkspaceCapability.METADATA_VALID,),
    *,
    include_state: bool = True,
) -> WorkspaceContext:
    """Resolve local workspace configuration and enforce requested local capabilities."""
    workspace_dir = resolve_workspace_dir(target_dir)
    config = load_workspace_config(workspace_dir)

    assessment = evaluate_workspace_assessment(workspace_dir, config)
    require_capabilities(
        assessment,
        *required_capabilities,
        workspace_dir=workspace_dir,
        config=config,
    )
    state = load_workspace_state(workspace_dir) if include_state else WorkspaceState()

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
