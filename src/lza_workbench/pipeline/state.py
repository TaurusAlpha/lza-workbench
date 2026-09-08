"""Operational state updates for pipeline executions."""

from __future__ import annotations

from datetime import UTC, datetime

from lza_workbench.pipeline.failures import PipelineActionFailure
from lza_workbench.pipeline.models import PipelineStageState
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
        state.installer_pipeline_execution_id = execution_id
        state.installer_pipeline_name = pipeline_name
        state.installer_pipeline_status = status
        state.installer_pipeline_failed_stage = None
        state.installer_pipeline_failed_action = None
        state.installer_pipeline_failed_build_url = None
        state.installer_pipeline_error = None
    else:
        state.config_pipeline_execution_id = execution_id
        state.config_pipeline_name = pipeline_name
        state.config_pipeline_status = status
        state.config_pipeline_failed_stage = None
        state.config_pipeline_failed_action = None
        state.config_pipeline_failed_build_url = None
        state.config_pipeline_error = None


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
    now = datetime.now(UTC)
    state.updated_at = now

    failed_stage: str | None = None
    failed_action: str | None = None
    failed_build_url: str | None = None
    resolved_error: str | None = None

    if status in {"Failed", "Cancelled", "TimedOut"}:
        if failed_actions:
            first_fa = failed_actions[0]
            failed_action = first_fa.action_name
            failed_build_url = first_fa.external_execution_url

            # Prioritize extracted actual error diagnostics from CloudWatch/CodeBuild
            diags = first_fa.diagnostic_details
            if diags:
                resolved_error = "\n".join(diags)
            else:
                resolved_error = (
                    first_fa.error_message or first_fa.summary
                )

            if stages:
                for st in stages:
                    st_name = getattr(st, "stage_name", "")
                    for act in getattr(st, "actions", []):
                        if getattr(act, "action_name", "") == failed_action:
                            failed_stage = st_name
                            break
                    if failed_stage:
                        break
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

    if pipeline_type == "installer":
        state.installer_pipeline_execution_id = execution_id
        state.installer_pipeline_name = pipeline_name
        state.installer_pipeline_status = status
        state.installer_pipeline_failed_stage = failed_stage
        state.installer_pipeline_failed_action = failed_action
        state.installer_pipeline_failed_build_url = failed_build_url
        state.installer_pipeline_error = resolved_error
    else:
        state.config_pipeline_execution_id = execution_id
        state.config_pipeline_name = pipeline_name
        state.config_pipeline_status = status
        state.config_pipeline_failed_stage = failed_stage
        state.config_pipeline_failed_action = failed_action
        state.config_pipeline_failed_build_url = failed_build_url
        state.config_pipeline_error = resolved_error


__all__ = [
    "record_pipeline_execution",
    "record_pipeline_watch_result",
]
