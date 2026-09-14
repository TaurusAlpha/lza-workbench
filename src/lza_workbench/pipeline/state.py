"""Operational state updates for pipeline executions."""

from __future__ import annotations

from datetime import UTC, datetime

from lza_workbench.pipeline.failures import PipelineActionFailure
from lza_workbench.pipeline.model import PipelineStageState
from lza_workbench.workspace.schema import WorkspaceState


def record_pipeline_execution(
    state: WorkspaceState,
    *,
    execution_id: str,
    pipeline_name: str,
    pipeline_type: str = "configuration",
    status: str = "InProgress",
) -> None:
    """Record a pipeline execution ID into workspace state."""
    now = datetime.now(UTC)
    state.updated_at = now
    if pipeline_type == "installer":
        recorded = state.pipelines.installer
    else:
        recorded = state.pipelines.configuration
    recorded.execution_id = execution_id
    recorded.name = pipeline_name
    recorded.status = status
    recorded.failed_stage = None
    recorded.failed_action = None
    recorded.failed_build_url = None
    recorded.error = None


def _find_stage_for_action(
    stages: list[PipelineStageState] | None, action_name: str | None
) -> str | None:
    if not stages or not action_name:
        return None
    for st in stages:
        st_name = getattr(st, "stage_name", "")
        for act in getattr(st, "actions", []):
            if getattr(act, "action_name", "") == action_name:
                return st_name
    return None


def _extract_watch_failure_details(
    *,
    status: str,
    stages: list[PipelineStageState] | None,
    failed_actions: list[PipelineActionFailure] | None,
    error_message: str | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    if status not in {"Failed", "Cancelled", "TimedOut"}:
        return None, None, None, None

    failed_stage: str | None = None
    failed_action: str | None = None
    failed_build_url: str | None = None
    resolved_error: str | None = None

    if failed_actions:
        first_fa = failed_actions[0]
        failed_action = first_fa.action_name
        failed_build_url = first_fa.external_execution_url
        diags = first_fa.diagnostic_details
        resolved_error = "\n".join(diags) if diags else (first_fa.error_message or first_fa.summary)
        failed_stage = _find_stage_for_action(stages, failed_action)
    elif stages:
        for st in stages:
            if st.status == "Failed":
                failed_stage = st.stage_name
                for act in st.actions:
                    if act.status == "Failed":
                        failed_action = act.action_name
                        failed_build_url = act.external_execution_url
                        resolved_error = act.error_message or act.summary
                        break
                break

    if not resolved_error:
        resolved_error = error_message

    return failed_stage, failed_action, failed_build_url, resolved_error


def record_pipeline_watch_result(
    state: WorkspaceState,
    *,
    execution_id: str,
    pipeline_name: str,
    status: str,
    stages: list[PipelineStageState] | None = None,
    failed_actions: list[PipelineActionFailure] | None = None,
    error_message: str | None = None,
    pipeline_type: str = "configuration",
) -> None:
    """Record execution completion, stage outcomes, and failure diagnostics in state."""
    state.updated_at = datetime.now(UTC)

    failed_stage, failed_action, failed_build_url, resolved_error = _extract_watch_failure_details(
        status=status,
        stages=stages,
        failed_actions=failed_actions,
        error_message=error_message,
    )

    if pipeline_type == "installer":
        recorded = state.pipelines.installer
    else:
        recorded = state.pipelines.configuration
    recorded.execution_id = execution_id
    recorded.name = pipeline_name
    recorded.status = status
    recorded.failed_stage = failed_stage
    recorded.failed_action = failed_action
    recorded.failed_build_url = failed_build_url
    recorded.error = resolved_error


__all__ = [
    "record_pipeline_execution",
    "record_pipeline_watch_result",
]
