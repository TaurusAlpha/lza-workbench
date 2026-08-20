"""AWS CodePipeline integration utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from lza_workbench.aws.client_factory import AwsClientFactory


@dataclass
class ActionStateResult:
    """State of an individual action inside a pipeline stage."""

    action_name: str
    status: str | None = None
    summary: str | None = None
    last_status_change: str | None = None
    error_message: str | None = None


@dataclass
class StageStateResult:
    """State of a pipeline stage."""

    stage_name: str
    status: str | None = None
    actions: list[ActionStateResult] = field(default_factory=list)


@dataclass
class PipelineStateResult:
    """Detailed status and stage execution state of an AWS CodePipeline."""

    pipeline_name: str
    exists: bool
    status: str | None = None
    stage_states: list[StageStateResult] = field(default_factory=list)
    latest_execution_id: str | None = None
    created: str | None = None
    updated: str | None = None
    error: str | None = None


def _get_codepipeline_client(
    factory: AwsClientFactory | None = None,
    client: Any | None = None,
) -> Any | None:
    if client is not None:
        return client
    if factory is not None:
        return factory.get_client("codepipeline")
    return None


def get_pipeline_state(
    *,
    client: Any | None = None,
    factory: AwsClientFactory | None = None,
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

    codepipeline = _get_codepipeline_client(factory=factory, client=client)
    if codepipeline is None:
        return PipelineStateResult(
            pipeline_name=clean_pipeline_name,
            exists=False,
            status="NOT_CHECKED",
            error="No AWS session available",
        )

    try:
        response = codepipeline.get_pipeline_state(name=clean_pipeline_name)
        stage_states_raw = response.get("stageStates", [])

        stage_results: list[StageStateResult] = []
        latest_execution_id: str | None = None

        has_in_progress = False
        has_failed = False
        has_cancelled = False
        has_stopped = False
        all_succeeded = bool(stage_states_raw)
        any_executed = False

        for stage in stage_states_raw:
            s_name = stage.get("stageName", "")
            latest_exec = stage.get("latestExecution") or {}
            s_status = latest_exec.get("status")
            s_exec_id = latest_exec.get("pipelineExecutionId")

            if s_exec_id and not latest_execution_id:
                latest_execution_id = s_exec_id

            actions: list[ActionStateResult] = []
            for action in stage.get("actionStates", []):
                a_name = action.get("actionName", "")
                a_exec = action.get("latestExecution") or {}
                a_status = a_exec.get("status")
                a_summary = a_exec.get("summary")
                a_time = (
                    str(a_exec.get("lastStatusChange"))
                    if a_exec.get("lastStatusChange")
                    else None
                )
                err_details = a_exec.get("errorDetails") or {}
                a_err = err_details.get("message")
                actions.append(
                    ActionStateResult(
                        action_name=a_name,
                        status=a_status,
                        summary=a_summary,
                        last_status_change=a_time,
                        error_message=a_err,
                    )
                )

            if s_status:
                any_executed = True
                if s_status == "InProgress":
                    has_in_progress = True
                    all_succeeded = False
                elif s_status == "Failed":
                    has_failed = True
                    all_succeeded = False
                elif s_status == "Cancelled":
                    has_cancelled = True
                    all_succeeded = False
                elif s_status in {"Stopped", "Stopping"}:
                    has_stopped = True
                    all_succeeded = False
                elif s_status != "Succeeded":
                    all_succeeded = False
            else:
                all_succeeded = False

            stage_results.append(
                StageStateResult(
                    stage_name=s_name,
                    status=s_status,
                    actions=actions,
                )
            )

        if not any_executed:
            derived_status = "Not Started"
        elif has_in_progress:
            derived_status = "InProgress"
        elif has_failed:
            derived_status = "Failed"
        elif has_cancelled:
            derived_status = "Cancelled"
        elif has_stopped:
            derived_status = "Stopped"
        elif all_succeeded:
            derived_status = "Succeeded"
        else:
            derived_status = "Unknown"

        created = str(response.get("created")) if response.get("created") else None
        updated = str(response.get("updated")) if response.get("updated") else None

        return PipelineStateResult(
            pipeline_name=clean_pipeline_name,
            exists=True,
            status=derived_status,
            stage_states=stage_results,
            latest_execution_id=latest_execution_id,
            created=created,
            updated=updated,
        )

    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if (
            code in {"PipelineNotFoundException", "ResourceNotFoundException"}
            or "does not exist" in str(exc)
        ):
            return PipelineStateResult(
                pipeline_name=clean_pipeline_name,
                exists=False,
                status="NOT_DEPLOYED",
            )
        return PipelineStateResult(
            pipeline_name=clean_pipeline_name,
            exists=False,
            status="UNKNOWN",
            error=str(exc),
        )
    except BotoCoreError as exc:
        return PipelineStateResult(
            pipeline_name=clean_pipeline_name,
            exists=False,
            status="UNKNOWN",
            error=f"Connection failure: {exc}",
        )
