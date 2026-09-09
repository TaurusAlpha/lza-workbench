"""AWS CodePipeline integration utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from lza_workbench.aws.errors import classify_aws_error
from lza_workbench.errors import LzaError


@dataclass(frozen=True)
class ActionStateResult:
    """Observed state of an action within a CodePipeline stage."""

    action_name: str
    stage_name: str | None = None
    status: str | None = None
    summary: str | None = None
    last_status_change: str | None = None
    error_message: str | None = None
    external_execution_id: str | None = None
    external_execution_url: str | None = None
    execution_id: str | None = None


@dataclass(frozen=True)
class StageStateResult:
    """Observed state of a CodePipeline stage and its actions."""

    stage_name: str
    status: str | None = None
    actions: list[ActionStateResult] = field(default_factory=list)
    execution_id: str | None = None


@dataclass(frozen=True)
class PipelineStateResult:
    """Detailed status and stage execution state of an AWS CodePipeline."""

    pipeline_name: str
    exists: bool
    status: str | None = None
    stages: list[StageStateResult] = field(default_factory=list)
    latest_execution_id: str | None = None
    created: str | None = None
    updated: str | None = None
    error: str | None = None

    @property
    def stage_states(self) -> list[StageStateResult]:
        """Backward-compatibility alias for stages."""
        return self.stages


@dataclass(frozen=True)
class PipelineExecutionResult:
    """Status and metadata of an AWS CodePipeline execution."""

    pipeline_name: str
    exists: bool = False
    execution_id: str = ""
    status: str = "UNKNOWN"
    status_summary: str | None = None
    start_time: str | None = None
    last_update_time: str | None = None
    duration_seconds: float | None = None
    error: str | None = None


def _parse_stage_state(stage: dict[str, Any]) -> StageStateResult:
    """Convert a CodePipeline stage-state response into an observation."""
    stage_name = stage.get("stageName", "")
    latest_execution = stage.get("latestExecution") or {}
    actions = [
        _parse_action_state(action, stage_name=stage_name)
        for action in stage.get("actionStates", [])
    ]
    return StageStateResult(
        stage_name=stage_name,
        status=latest_execution.get("status"),
        actions=actions,
        execution_id=latest_execution.get("pipelineExecutionId"),
    )


def _parse_action_state(action: dict[str, Any], *, stage_name: str) -> ActionStateResult:
    """Convert a CodePipeline action-state response into an observation."""
    latest_execution = action.get("latestExecution") or {}
    last_status_change = latest_execution.get("lastStatusChange")
    error_details = latest_execution.get("errorDetails") or {}
    return ActionStateResult(
        action_name=action.get("actionName", ""),
        stage_name=stage_name,
        status=latest_execution.get("status"),
        summary=latest_execution.get("summary"),
        last_status_change=str(last_status_change) if last_status_change else None,
        error_message=error_details.get("message"),
        external_execution_id=latest_execution.get("externalExecutionId"),
        external_execution_url=latest_execution.get("externalExecutionUrl"),
        execution_id=latest_execution.get("pipelineExecutionId"),
    )


def _derive_pipeline_status(stages: list[StageStateResult]) -> str:
    """Derive the pipeline status using CodePipeline stage-state precedence."""
    statuses = {stage.status for stage in stages if stage.status}
    if not statuses:
        return "Not Started"
    if "InProgress" in statuses:
        return "InProgress"
    if "Failed" in statuses:
        return "Failed"
    if "Cancelled" in statuses:
        return "Cancelled"
    if statuses & {"Stopped", "Stopping"}:
        return "Stopped"
    if all(stage.status == "Succeeded" for stage in stages):
        return "Succeeded"
    return "Unknown"


def get_pipeline_state(
    *,
    client: Any,
    pipeline_name: str,
) -> PipelineStateResult:
    """Get CodePipeline state and stage statuses without mutating AWS."""
    clean_pipeline_name = (pipeline_name or "").strip()
    if not clean_pipeline_name:
        return PipelineStateResult(
            pipeline_name="",
            exists=False,
            status="NOT_SPECIFIED",
            error="Pipeline name is empty",
        )

    if not client:
        return PipelineStateResult(
            pipeline_name=clean_pipeline_name,
            exists=False,
            status="UNKNOWN",
            error="Connection failure: client is not initialized",
        )
    try:
        response = client.get_pipeline_state(name=clean_pipeline_name)
        stage_states_raw = response.get("stageStates", [])

        stage_results = [_parse_stage_state(stage) for stage in stage_states_raw]
        latest_execution_id: str | None = None
        for stage in stage_results:
            if stage.execution_id:
                latest_execution_id = stage.execution_id
                break

        created = str(response.get("created")) if response.get("created") else None
        updated = str(response.get("updated")) if response.get("updated") else None

        return PipelineStateResult(
            pipeline_name=clean_pipeline_name,
            exists=True,
            status=_derive_pipeline_status(stage_results),
            stages=stage_results,
            latest_execution_id=latest_execution_id,
            created=created,
            updated=updated,
        )

    except Exception as exc:
        info = classify_aws_error(exc)
        if info.is_not_found:
            return PipelineStateResult(
                pipeline_name=clean_pipeline_name,
                exists=False,
                status="NOT_DEPLOYED",
            )
        prefix = "Connection failure: " if info.is_unavailable else ""
        return PipelineStateResult(
            pipeline_name=clean_pipeline_name,
            exists=False,
            status="UNKNOWN",
            error=f"{prefix}{info.message}",
        )


def start_pipeline_execution(
    *,
    client: Any,
    pipeline_name: str,
) -> str:
    """Trigger a new CodePipeline execution and return the execution ID."""
    clean_pipeline_name = (pipeline_name or "").strip()
    if not clean_pipeline_name:
        raise LzaError("Pipeline name cannot be empty.")

    try:
        response = client.start_pipeline_execution(name=clean_pipeline_name)
        execution_id = response.get("pipelineExecutionId")
        if not execution_id:
            raise LzaError(f"No pipeline execution ID returned for '{clean_pipeline_name}'.")
        return str(execution_id)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        message = exc.response.get("Error", {}).get("Message", str(exc))
        if code in {"PipelineNotFoundException", "ResourceNotFoundException"}:
            raise LzaError(f"Pipeline '{clean_pipeline_name}' does not exist.") from exc
        if code == "ConflictException":
            raise LzaError(
                f"Cannot start execution for pipeline '{clean_pipeline_name}': {message}"
            ) from exc
        raise LzaError(f"Failed to start CodePipeline '{clean_pipeline_name}': {message}") from exc
    except BotoCoreError as exc:
        raise LzaError(f"AWS connection failure when starting pipeline: {exc}") from exc


def get_pipeline_execution(
    *,
    client: Any,
    pipeline_name: str,
    execution_id: str,
) -> PipelineExecutionResult:
    """Fetch status and metadata for a specific CodePipeline execution."""
    clean_pipeline_name = (pipeline_name or "").strip()
    clean_execution_id = (execution_id or "").strip()
    if not clean_pipeline_name or not clean_execution_id:
        return PipelineExecutionResult(
            pipeline_name=clean_pipeline_name,
            exists=False,
            execution_id=clean_execution_id,
            status="UNKNOWN",
            error="Pipeline name or execution ID is empty",
        )

    try:
        response = client.get_pipeline_execution(
            pipelineName=clean_pipeline_name,
            pipelineExecutionId=clean_execution_id,
        )
        execution = response.get("pipelineExecution", {})
        status = execution.get("status", "Unknown")
        status_summary = execution.get("statusSummary")
        raw_start = execution.get("startTime")
        raw_update = execution.get("lastUpdateTime")
        start_time = str(raw_start) if raw_start else None
        last_update_time = str(raw_update) if raw_update else None

        duration_seconds: float | None = None
        if isinstance(raw_start, datetime) and isinstance(raw_update, datetime):
            duration_seconds = max(0.0, (raw_update - raw_start).total_seconds())
        elif raw_start and raw_update:
            try:
                st = datetime.fromisoformat(str(raw_start).replace("Z", "+00:00"))
                ut = datetime.fromisoformat(str(raw_update).replace("Z", "+00:00"))
                duration_seconds = max(0.0, (ut - st).total_seconds())
            except Exception:
                duration_seconds = None

        return PipelineExecutionResult(
            pipeline_name=clean_pipeline_name,
            exists=True,
            execution_id=clean_execution_id,
            status=status,
            status_summary=status_summary,
            start_time=start_time,
            last_update_time=last_update_time,
            duration_seconds=duration_seconds,
        )

    except Exception as exc:
        info = classify_aws_error(exc)
        if info.is_not_found:
            return PipelineExecutionResult(
                pipeline_name=clean_pipeline_name,
                exists=False,
                execution_id=clean_execution_id,
                status="NOT_FOUND",
                error=info.message,
            )
        prefix = "Connection failure: " if info.is_unavailable else ""
        return PipelineExecutionResult(
            pipeline_name=clean_pipeline_name,
            exists=False,
            execution_id=clean_execution_id,
            status="UNKNOWN",
            error=f"{prefix}{info.message}",
        )


def get_latest_pipeline_execution_id(
    *,
    client: Any,
    pipeline_name: str,
) -> str | None:
    """Discover the most recent execution ID for a pipeline."""
    clean_pipeline_name = (pipeline_name or "").strip()
    if not clean_pipeline_name:
        return None

    try:
        response = client.list_pipeline_executions(
            pipelineName=clean_pipeline_name,
            maxResults=1,
        )
        summaries = response.get("pipelineExecutionSummaries", [])
        if summaries:
            return str(summaries[0].get("pipelineExecutionId"))
    except (ClientError, BotoCoreError):
        pass

    # Fallback to get_pipeline_state
    state = get_pipeline_state(client=client, pipeline_name=clean_pipeline_name)
    return state.latest_execution_id


__all__ = [
    "ActionStateResult",
    "PipelineExecutionResult",
    "PipelineStateResult",
    "StageStateResult",
    "get_latest_pipeline_execution_id",
    "get_pipeline_execution",
    "get_pipeline_state",
    "start_pipeline_execution",
]
