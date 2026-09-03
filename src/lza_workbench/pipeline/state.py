"""Operational state updates for pipeline executions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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
    stages: list[Any] | None = None,
    failed_actions: list[Any] | None = None,
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
            failed_action = getattr(first_fa, "action_name", str(first_fa))
            failed_build_url = getattr(first_fa, "external_execution_url", None)

            # Prioritize extracted actual error diagnostics from CloudWatch/CodeBuild
            diags = getattr(first_fa, "diagnostic_details", [])
            if diags:
                resolved_error = "\n".join(diags)
            else:
                resolved_error = (
                    getattr(first_fa, "error_message", None)
                    or getattr(first_fa, "summary", None)
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
                if getattr(st, "status", "") == "Failed":
                    failed_stage = getattr(st, "stage_name", None)
                    for act in getattr(st, "actions", []):
                        if getattr(act, "status", "") == "Failed":
                            failed_action = getattr(act, "action_name", None)
                            failed_build_url = getattr(act, "external_execution_url", None)
                            diags = getattr(act, "diagnostic_details", [])
                            if diags:
                                resolved_error = "\n".join(diags)
                            else:
                                resolved_error = (
                                    getattr(act, "error_message", None)
                                    or getattr(act, "summary", None)
                                )
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

