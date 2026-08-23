"""Operational state updates for pipeline executions."""

from __future__ import annotations

from datetime import UTC, datetime

from lza_workbench.workspace.schema import WorkspaceState


def record_pipeline_execution(
    state: WorkspaceState,
    *,
    execution_id: str,
    pipeline_type: str = "configuration",
) -> None:
    """Record a pipeline execution ID into workspace state."""
    now = datetime.now(UTC)
    state.updated_at = now
    if pipeline_type == "installer":
        state.installer_pipeline_execution_id = execution_id
    else:
        state.config_pipeline_execution_id = execution_id


__all__ = ["record_pipeline_execution"]
