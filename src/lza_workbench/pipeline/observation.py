"""Single-pass pipeline execution observation."""

from __future__ import annotations

from typing import Any

from lza_workbench.aws.codepipeline import get_pipeline_execution, get_pipeline_state
from lza_workbench.pipeline.models import PipelineExecutionSnapshot, PipelineStageState


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
        return execution

    pipeline_state = get_pipeline_state(client=client, pipeline_name=pipeline_name)
    stages: list[PipelineStageState] = []
    for stage in pipeline_state.stages:
        if stage.execution_id and stage.execution_id != execution_id:
            continue
        actions = [
            action
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


__all__ = ["observe_pipeline_execution"]
