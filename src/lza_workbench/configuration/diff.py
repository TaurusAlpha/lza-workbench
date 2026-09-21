"""Application use case for showing configuration diffs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lza_workbench.configuration.archive import ConfigDiffResult
from lza_workbench.workspace.context import load_workspace_context
from lza_workbench.workspace.validation import WorkspaceCapability


@dataclass(frozen=True)
class ConfigDiffExecutionResult:
    workspace_dir: Path
    config_dir: Path
    diff_result: ConfigDiffResult | None = None
    remote_type: str = "unknown"


def diff_configuration(
    *,
    workspace_dir: Path | None = None,
) -> ConfigDiffExecutionResult:
    ctx = load_workspace_context(
        target_dir=workspace_dir,
        required_capabilities=(
            WorkspaceCapability.METADATA_VALID,
            WorkspaceCapability.CONFIGURATION_PRESENT,
        ),
    )
    return ConfigDiffExecutionResult(
        workspace_dir=ctx.workspace_dir,
        config_dir=ctx.config_dir,
        remote_type=ctx.config.configuration.repository.type,
    )


__all__ = [
    "ConfigDiffExecutionResult",
    "diff_configuration",
]
