"""Single-pass pipeline execution observation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from lza_workbench.infrastructure.aws.codepipeline import (
    PipelineStateResult,
    StageStateResult,
    get_latest_pipeline_execution,
    get_pipeline_execution,
    get_pipeline_state,
)
from lza_workbench.infrastructure.aws.errors import (
    ObservationOutcome,
    outcome_from_aws_error,
)
from lza_workbench.pipeline.failures import (
    collect_pipeline_action_failures,
    fetch_codebuild_diagnostics,
)
from lza_workbench.pipeline.model import (
    PipelineActionState,
    PipelineExecutionSnapshot,
    PipelineStageState,
    PipelineSummary,
)

if TYPE_CHECKING:
    from lza_workbench.infrastructure.aws.session import AwsClientFactory
    from lza_workbench.workspace.schema import WorkspaceState


def stage_state_to_pipeline_stage(stage: StageStateResult) -> PipelineStageState:
    return PipelineStageState(
        stage_name=stage.stage_name,
        status=stage.status,
        execution_id=stage.execution_id,
        actions=[
            PipelineActionState(
                action_name=action.action_name,
                stage_name=stage.stage_name,
                status=action.status,
                summary=action.summary,
                last_status_change=action.last_status_change,
                error_message=action.error_message,
                external_execution_id=action.external_execution_id,
                external_execution_url=action.external_execution_url,
                execution_id=action.execution_id,
            )
            for action in stage.actions
        ],
    )


def pipeline_state_to_snapshot(state_result: PipelineStateResult) -> PipelineExecutionSnapshot:
    return PipelineExecutionSnapshot(
        pipeline_name=state_result.pipeline_name,
        exists=state_result.exists,
        status=state_result.status,
        execution_id=state_result.latest_execution_id,
        stages=[stage_state_to_pipeline_stage(s) for s in state_result.stages],
        created=state_result.created,
        updated=state_result.updated,
        error=state_result.error,
    )


def observe_pipeline_execution(
    *,
    client: Any,
    pipeline_name: str,
    execution_id: str,
) -> PipelineExecutionSnapshot:
    """Read one execution and its matching stage/action states without diagnostics or writes."""
    execution = get_pipeline_execution(
        client=client,
        pipeline_name=pipeline_name,
        execution_id=execution_id,
    )
    if execution.status == "NOT_FOUND":
        return PipelineExecutionSnapshot(
            pipeline_name=execution.pipeline_name,
            exists=False,
            status="NOT_FOUND",
            execution_id=execution.execution_id,
            error=execution.error,
        )

    pipeline_state = get_pipeline_state(client=client, pipeline_name=pipeline_name)
    stages: list[PipelineStageState] = []
    for stage in pipeline_state.stages:
        if stage.execution_id and stage.execution_id != execution_id:
            continue
        actions = [
            PipelineActionState(
                action_name=action.action_name,
                stage_name=stage.stage_name,
                status=action.status,
                summary=action.summary,
                last_status_change=action.last_status_change,
                error_message=action.error_message,
                external_execution_id=action.external_execution_id,
                external_execution_url=action.external_execution_url,
                execution_id=action.execution_id,
            )
            for action in stage.actions
            if not action.execution_id or action.execution_id == execution_id
        ]
        stages.append(
            PipelineStageState(
                stage_name=stage.stage_name,
                status=stage.status,
                actions=actions,
                execution_id=stage.execution_id,
            )
        )

    return PipelineExecutionSnapshot(
        pipeline_name=execution.pipeline_name,
        exists=execution.exists,
        status=execution.status,
        execution_id=execution.execution_id,
        stages=stages,
        status_summary=execution.status_summary,
        start_time=execution.start_time,
        last_update_time=execution.last_update_time,
        duration_seconds=execution.duration_seconds,
        error=execution.error,
    )


def _resolve_in_progress_stage_action(
    stages: list[PipelineStageState],
) -> tuple[str | None, str | None]:
    for stage in stages:
        if stage.status == "InProgress":
            for act in stage.actions:
                if act.status == "InProgress":
                    return stage.stage_name, act.action_name
            action_name = stage.actions[0].action_name if stage.actions else None
            return stage.stage_name, action_name
    return None, None


def _resolve_pipeline_failure_details(
    stages: list[PipelineStageState],
    factory: AwsClientFactory | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    codebuild_client = factory.get_client("codebuild") if factory else None
    logs_client = factory.get_client("logs") if factory else None
    failures = collect_pipeline_action_failures(
        stages,
        fetch_diagnostics=lambda build_id: (
            fetch_codebuild_diagnostics(
                codebuild_client=codebuild_client,
                logs_client=logs_client,
                build_id=build_id,
            )
            if codebuild_client
            else []
        ),
    )
    if not failures:
        return None, None, None, None
    failed_stage = failures[0].stage_name
    failed_action = failures[0].action_name
    failed_build_url = failures[0].external_execution_url
    if failures[0].diagnostic_details:
        summary = failures[0].diagnostic_details[0]
    else:
        summary = failures[0].error_message or failures[0].summary
    return failed_stage, failed_action, summary, failed_build_url


def observe_pipeline_status(
    *,
    pipeline_name: str,
    pipeline_type: str = "configuration",
    factory: AwsClientFactory | None = None,
    codepipeline_client: Any | None = None,
    state: WorkspaceState | None = None,
    fetch_diagnostics: bool = True,
    target_execution_id: str | None = None,
) -> PipelineSummary:
    """Collect unified pipeline observation with live query, failure diagnostics, and offline fallback."""
    now = datetime.now(UTC)
    resolved_client = codepipeline_client or (factory.get_client("codepipeline") if factory else None)

    if resolved_client is not None:
        pipe_state = get_pipeline_state(client=resolved_client, pipeline_name=pipeline_name)
        if pipe_state.error:
            # Query returned an error
            outcome = (
                outcome_from_aws_error(pipe_state.error_info)
                if pipe_state.error_info is not None
                else ObservationOutcome.COLLECTION_FAILED
            )
            is_not_found = (
                pipe_state.error_info.is_not_found
                if pipe_state.error_info is not None
                else False
            )
            if is_not_found or pipe_state.status == "NOT_DEPLOYED":
                return PipelineSummary(
                    name=pipeline_name,
                    exists=False,
                    status="Not Deployed",
                    is_live=True,
                    outcome=ObservationOutcome.ABSENT,
                    observed_at=now,
                    last_attempt_at=now,
                    error=None,
                    raw_state=pipe_state,
                )
            # Non-not-found error: fall back to recorded observation while recording attempt and error
            obs = (
                state.pipelines.track(pipeline_type).resolve_offline_observation()
                if state is not None and pipeline_type in {"installer", "configuration"}
                else None
            )
            if obs is not None:
                exists = (
                    obs.exists
                    if obs.exists is not None
                    else (obs.status not in (None, "Not Deployed", "NOT_DEPLOYED"))
                )
                return PipelineSummary(
                    name=pipeline_name,
                    exists=exists,
                    status=obs.status,
                    execution_id=obs.execution_id,
                    failed_stage=obs.failed_stage,
                    failed_action=obs.failed_action,
                    failed_build_url=obs.failed_build_url,
                    failure_summary=obs.error,
                    is_live=False,
                    outcome=outcome,
                    observed_at=obs.observed_at,
                    last_attempt_at=now,
                    error=pipe_state.error or obs.last_attempt_error,
                    raw_state=pipe_state,
                )
            return PipelineSummary(
                name=pipeline_name,
                exists=False,
                status=None,
                execution_id=None,
                is_live=False,
                outcome=outcome,
                observed_at=None,
                last_attempt_at=now,
                error=pipe_state.error,
                raw_state=pipe_state,
            )

        if not pipe_state.exists:
            return PipelineSummary(
                name=pipeline_name,
                exists=False,
                status="Not Deployed",
                is_live=True,
                outcome=ObservationOutcome.ABSENT,
                observed_at=now,
                last_attempt_at=now,
                raw_state=pipe_state,
            )

        status = pipe_state.status
        execution_id = target_execution_id or pipe_state.latest_execution_id
        start_time: str | None = None
        duration_seconds: float | None = None

        if execution_id:
            exec_res = get_latest_pipeline_execution(
                client=resolved_client,
                pipeline_name=pipeline_name,
            )
            if exec_res and exec_res.execution_id == execution_id:
                start_time = exec_res.start_time
                duration_seconds = exec_res.duration_seconds

        stages = [stage_state_to_pipeline_stage(s) for s in pipe_state.stages]
        current_stage, current_action = (
            _resolve_in_progress_stage_action(stages)
            if status == "InProgress"
            else (None, None)
        )

        failed_stage, failed_action, failure_summary, failed_build_url = (
            None,
            None,
            None,
            None,
        )
        if status in {"Failed", "Cancelled"} and fetch_diagnostics:
            (
                failed_stage,
                failed_action,
                failure_summary,
                failed_build_url,
            ) = _resolve_pipeline_failure_details(stages, factory)

        return PipelineSummary(
            name=pipeline_name,
            exists=True,
            status=status,
            execution_id=execution_id,
            start_time=start_time,
            duration_seconds=duration_seconds,
            current_stage=current_stage,
            current_action=current_action,
            failed_stage=failed_stage,
            failed_action=failed_action,
            failure_summary=failure_summary,
            failed_build_url=failed_build_url,
            stages=stages,
            raw_state=pipe_state,
            is_live=True,
            outcome=ObservationOutcome.OBSERVED,
            observed_at=now,
            last_attempt_at=now,
        )

    # Factory / Client not available: fall back to recorded state
    obs = (
        state.pipelines.track(pipeline_type).resolve_offline_observation()
        if state is not None and pipeline_type in {"installer", "configuration"}
        else None
    )
    if obs is not None:
        exists = (
            obs.exists
            if obs.exists is not None
            else (obs.status not in (None, "Not Deployed", "NOT_DEPLOYED"))
        )
        return PipelineSummary(
            name=pipeline_name,
            exists=exists,
            status=obs.status,
            execution_id=obs.execution_id,
            failed_stage=obs.failed_stage,
            failed_action=obs.failed_action,
            failed_build_url=obs.failed_build_url,
            failure_summary=obs.error,
            is_live=False,
            outcome=ObservationOutcome.NOT_COLLECTED,
            observed_at=obs.observed_at,
            last_attempt_at=obs.last_attempt_at,
            error=obs.last_attempt_error,
        )

    return PipelineSummary(
        name=pipeline_name,
        exists=False,
        status=None,
        execution_id=None,
        is_live=False,
        outcome=ObservationOutcome.NOT_COLLECTED,
    )


__all__ = [
    "observe_pipeline_execution",
    "observe_pipeline_status",
    "pipeline_state_to_snapshot",
    "stage_state_to_pipeline_stage",
]
