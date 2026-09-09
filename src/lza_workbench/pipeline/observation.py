"""Single-pass pipeline execution observation."""

from __future__ import annotations

from typing import Any

from lza_workbench.aws.codepipeline import (
    PipelineStateResult,
    StageStateResult,
    get_pipeline_execution,
    get_pipeline_state,
)
from lza_workbench.pipeline.models import (
    PipelineActionState,
    PipelineExecutionSnapshot,
    PipelineStageState,
)


def stage_state_to_pipeline_stage(stage: StageStateResult) -> PipelineStageState:
    """Convert an AWS StageStateResult to a canonical PipelineStageState."""
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
    """Convert an AWS PipelineStateResult to a canonical PipelineExecutionSnapshot."""
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


__all__ = [
    "observe_pipeline_execution",
    "pipeline_state_to_snapshot",
    "stage_state_to_pipeline_stage",
]
