"""Workflow for single-pass pipeline execution snapshots and diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from typing import Any

from lza_workbench.aws.codepipeline import (
    get_latest_pipeline_execution_id,
    get_pipeline_state,
)
from lza_workbench.aws.context import AwsExecutionContext, resolve_aws_execution_context
from lza_workbench.pipeline.failures import (
    PipelineActionFailure,
    collect_pipeline_action_failures,
    fetch_codebuild_diagnostics,
)
from lza_workbench.pipeline.models import PipelineStageState
from lza_workbench.pipeline.observation import (
    PipelineExecutionSnapshot,
    observe_pipeline_execution,
    pipeline_state_to_snapshot,
)
from lza_workbench.pipeline.resolution import resolve_pipeline
from lza_workbench.workspace.context import (
    WorkspaceCapability,
    WorkspaceContext,
    load_workspace_context,
)
from lza_workbench.workspace.schema import WorkspaceState

TERMINAL_STATUSES = {"Succeeded", "Failed", "Cancelled", "Stopped", "Superseded"}


@dataclass(frozen=True)
class PipelineSnapshotResult:
    """Structured result of single-pass pipeline execution observation."""

    workspace_dir: Path
    customer_name: str
    pipeline_name: str
    pipeline_type: str
    pipeline_arn: str
    execution_id: str | None
    status: str
    status_summary: str | None
    is_terminal: bool
    stages: list[PipelineStageState] = field(default_factory=list)
    start_time: str | None = None
    last_update_time: str | None = None
    duration_seconds: float | None = None
    current_stage: str | None = None
    current_action: str | None = None
    failed_stage: str | None = None
    failed_action: str | None = None
    is_live: bool = True
    error: str | None = None


def _build_offline_pipeline_snapshot(
    *,
    workspace_dir: Path,
    customer_name: str,
    pipeline_name: str,
    pipeline_type: str,
    pipeline_arn: str,
    execution_id: str | None,
    state: WorkspaceState,
    aws_error: str | None,
) -> PipelineSnapshotResult:
    recorded_status = (
        state.config_pipeline_status
        if pipeline_type == "configuration"
        else state.installer_pipeline_status
    ) or "Unknown"
    recorded_exec_id = (
        execution_id
        or (
            state.config_pipeline_execution_id
            if pipeline_type == "configuration"
            else state.installer_pipeline_execution_id
        )
    )
    return PipelineSnapshotResult(
        workspace_dir=workspace_dir,
        customer_name=customer_name,
        pipeline_name=pipeline_name,
        pipeline_type=pipeline_type,
        pipeline_arn=pipeline_arn,
        execution_id=recorded_exec_id,
        status=recorded_status,
        status_summary="Offline - reflecting last recorded state",
        is_terminal=True,
        is_live=False,
        error=aws_error,
    )


def _find_active_and_failed_actions(
    stages: list[PipelineStageState],
) -> tuple[str | None, str | None, str | None, str | None]:
    current_stage: str | None = None
    current_action: str | None = None
    failed_stage: str | None = None
    failed_action: str | None = None

    for stage in stages:
        if stage.status == "InProgress" and not current_stage:
            current_stage = stage.stage_name
            for action in stage.actions:
                if action.status == "InProgress":
                    current_action = action.action_name
                    break
        elif stage.status == "Failed" and not failed_stage:
            failed_stage = stage.stage_name
            for action in stage.actions:
                if action.status == "Failed":
                    failed_action = action.action_name
                    break

    return current_stage, current_action, failed_stage, failed_action


def _resolve_pipeline_snapshot_data(
    codepipeline_client: Any,
    pipeline_name: str,
    execution_id: str | None,
) -> PipelineExecutionSnapshot:
    target_exec_id = execution_id
    if not target_exec_id:
        target_exec_id = get_latest_pipeline_execution_id(
            client=codepipeline_client, pipeline_name=pipeline_name
        )

    if target_exec_id:
        return observe_pipeline_execution(
            client=codepipeline_client,
            pipeline_name=pipeline_name,
            execution_id=target_exec_id,
        )

    state_result = get_pipeline_state(
        client=codepipeline_client, pipeline_name=pipeline_name
    )
    return pipeline_state_to_snapshot(state_result)


def get_pipeline_snapshot_workflow(
    *,
    target_dir: Path | None = None,
    pipeline_type: str = "configuration",
    execution_id: str | None = None,
    workspace_context: WorkspaceContext | None = None,
    aws_context: AwsExecutionContext | None = None,
) -> PipelineSnapshotResult:
    """Retrieve an instant snapshot of pipeline execution status and stages."""
    ctx = workspace_context or load_workspace_context(
        target_dir, required_capabilities=(WorkspaceCapability.METADATA_VALID,)
    )
    config = ctx.config
    state = ctx.state
    workspace_dir = ctx.workspace_dir

    pipeline = resolve_pipeline(config, pipeline_type=pipeline_type)
    resolved_pipeline_name = pipeline.name

    resolved_aws = aws_context or resolve_aws_execution_context(
        profile=config.aws.profile or "",
        region=config.aws.region,
        role_arn=config.aws.role_arn,
        expected_account_id=config.aws.account_id,
        prime_credentials=config.aws.prime_credentials,
    )

    region = resolved_aws.region
    account_id = (
        resolved_aws.identity["account"] if resolved_aws.identity else "UNKNOWN_ACCOUNT"
    )
    pipeline_arn = pipeline.arn(region=region, account_id=account_id)

    if not resolved_aws.is_live:
        return _build_offline_pipeline_snapshot(
            workspace_dir=workspace_dir,
            customer_name=config.customer.name,
            pipeline_name=resolved_pipeline_name,
            pipeline_type=pipeline_type,
            pipeline_arn=pipeline_arn,
            execution_id=execution_id,
            state=state,
            aws_error=resolved_aws.error,
        )

    codepipeline_client = resolved_aws.factory.get_client("codepipeline")
    snapshot = _resolve_pipeline_snapshot_data(
        codepipeline_client=codepipeline_client,
        pipeline_name=resolved_pipeline_name,
        execution_id=execution_id,
    )

    status = snapshot.status or "Unknown"
    is_terminal = status in TERMINAL_STATUSES
    current_stage, current_action, failed_stage, failed_action = (
        _find_active_and_failed_actions(snapshot.stages)
    )

    return PipelineSnapshotResult(
        workspace_dir=workspace_dir,
        customer_name=config.customer.name,
        pipeline_name=resolved_pipeline_name,
        pipeline_type=pipeline_type,
        pipeline_arn=pipeline_arn,
        execution_id=snapshot.execution_id,
        status=status,
        status_summary=snapshot.status_summary,
        is_terminal=is_terminal,
        stages=snapshot.stages,
        start_time=snapshot.start_time,
        last_update_time=snapshot.last_update_time,
        duration_seconds=snapshot.duration_seconds,
        current_stage=current_stage,
        current_action=current_action,
        failed_stage=failed_stage,
        failed_action=failed_action,
        is_live=True,
        error=snapshot.error,
    )



def get_pipeline_diagnostics_workflow(
    *,
    target_dir: Path | None = None,
    pipeline_type: str = "configuration",
    execution_id: str | None = None,
    workspace_context: WorkspaceContext | None = None,
    aws_context: AwsExecutionContext | None = None,
) -> list[PipelineActionFailure]:
    """Retrieve enriched root-cause failure diagnostics for a pipeline execution."""
    snapshot = get_pipeline_snapshot_workflow(
        target_dir=target_dir,
        pipeline_type=pipeline_type,
        execution_id=execution_id,
        workspace_context=workspace_context,
        aws_context=aws_context,
    )
    if not snapshot.stages or not snapshot.is_live:
        return []

    ctx = workspace_context or load_workspace_context(
        target_dir, required_capabilities=(WorkspaceCapability.METADATA_VALID,)
    )
    config = ctx.config
    resolved_aws = aws_context or resolve_aws_execution_context(
        profile=config.aws.profile or "",
        region=config.aws.region,
        role_arn=config.aws.role_arn,
        expected_account_id=config.aws.account_id,
        prime_credentials=config.aws.prime_credentials,
    )
    if not resolved_aws.is_live:
        return []

    codebuild_client = resolved_aws.factory.get_client("codebuild")
    logs_client = resolved_aws.factory.get_client("logs")
    return collect_pipeline_action_failures(
        snapshot.stages,
        fetch_diagnostics=lambda build_id: fetch_codebuild_diagnostics(
            codebuild_client=codebuild_client,
            logs_client=logs_client,
            build_id=build_id,
        ),
    )


__all__ = [
    "PipelineActionFailure",
    "PipelineSnapshotResult",
    "TERMINAL_STATUSES",
    "get_pipeline_diagnostics_workflow",
    "get_pipeline_snapshot_workflow",
]
