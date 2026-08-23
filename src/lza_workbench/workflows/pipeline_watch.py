"""Workflow for monitoring AWS CodePipeline executions."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from lza_workbench.aws.codepipeline import (
    get_latest_pipeline_execution_id,
    get_pipeline_execution,
    get_pipeline_state,
)
from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.errors import LzaError
from lza_workbench.workspace.context import (
    WorkspaceReadinessLevel,
    load_workspace_context,
)


@dataclass(frozen=True)
class PipelineActionSummary:
    """Status and error details of an individual action inside a pipeline stage."""

    action_name: str
    status: str | None = None
    summary: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class PipelineStageSummary:
    """Status and nested actions of a pipeline stage."""

    stage_name: str
    status: str | None = None
    actions: list[PipelineActionSummary] = field(default_factory=list)


@dataclass(frozen=True)
class PipelineWatchUpdate:
    """Progress update emitted during pipeline polling."""

    pipeline_name: str
    execution_id: str
    status: str
    stages: list[PipelineStageSummary]
    elapsed_seconds: float


@dataclass(frozen=True)
class PipelineWatchResult:
    """Final structured result of watching a pipeline execution."""

    workspace_dir: Path
    customer_name: str
    pipeline_name: str
    pipeline_arn: str
    execution_id: str
    status: str
    stages: list[PipelineStageSummary]
    failed_actions: list[PipelineActionSummary]
    elapsed_seconds: float
    error_message: str | None = None


TERMINAL_STATUSES = {"Succeeded", "Failed", "Cancelled", "Stopped", "Superseded"}


def watch_pipeline_workflow(
    *,
    target_dir: Path | None = None,
    pipeline_name: str | None = None,
    pipeline_type: str = "configuration",
    execution_id: str | None = None,
    poll_interval_seconds: int | None = None,
    timeout_seconds: int | None = 7200,
    sleeper: Callable[[float], None] = time.sleep,
    time_provider: Callable[[], float] = time.time,
    on_update: Callable[[PipelineWatchUpdate], None] | None = None,
) -> PipelineWatchResult:
    """Monitor a CodePipeline execution until completion or timeout."""
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED)
    workspace_dir, config, state = ctx.workspace_dir, ctx.config, ctx.state

    prefix = config.lza.accelerator_prefix or "AWSAccelerator"
    if pipeline_name:
        resolved_pipeline_name = pipeline_name.strip()
    elif pipeline_type == "installer":
        resolved_pipeline_name = config.pipelines.installer.name or f"{prefix}-Installer"
    else:
        resolved_pipeline_name = config.pipelines.configuration.name or f"{prefix}-Pipeline"

    profile = config.aws.profile or ""
    aws_context = resolve_aws_execution_context(
        profile=profile,
        region=config.aws.region,
        role_arn=config.aws.role_arn,
        expected_account_id=config.aws.account_id,
        require_identity=True,
        require_expected_account=True,
    )

    region = aws_context.region
    account_id = aws_context.identity["account"] if aws_context.identity else "UNKNOWN_ACCOUNT"
    pipeline_arn = f"arn:aws:codepipeline:{region}:{account_id}:{resolved_pipeline_name}"
    client = aws_context.factory.get_client("codepipeline")

    resolved_execution_id = execution_id
    if not resolved_execution_id:
        if pipeline_type == "installer" and state.installer_pipeline_execution_id:
            resolved_execution_id = state.installer_pipeline_execution_id
        elif pipeline_type == "configuration" and state.config_pipeline_execution_id:
            resolved_execution_id = state.config_pipeline_execution_id
        else:
            resolved_execution_id = get_latest_pipeline_execution_id(
                client=client,
                pipeline_name=resolved_pipeline_name,
            )

    if not resolved_execution_id:
        raise LzaError(
            f"No execution found to watch for pipeline '{resolved_pipeline_name}'. "
            "Start a pipeline execution before watching."
        )

    interval = poll_interval_seconds
    if interval is None:
        interval = config.pipelines.configuration.poll_interval_seconds or 15

    start_time = time_provider()
    last_status = "InProgress"
    stage_summaries: list[PipelineStageSummary] = []
    failed_actions: list[PipelineActionSummary] = []
    error_message: str | None = None

    while True:
        elapsed = time_provider() - start_time
        if timeout_seconds and elapsed > timeout_seconds:
            last_status = "TimedOut"
            error_message = f"Watch timed out after {int(elapsed)} seconds."
            break

        exec_res = get_pipeline_execution(
            client=client,
            pipeline_name=resolved_pipeline_name,
            execution_id=resolved_execution_id,
        )

        state_res = get_pipeline_state(
            client=client,
            pipeline_name=resolved_pipeline_name,
        )

        stage_summaries = []
        failed_actions = []
        for s in state_res.stage_states:
            actions: list[PipelineActionSummary] = []
            for a in s.actions:
                action_sum = PipelineActionSummary(
                    action_name=a.action_name,
                    status=a.status,
                    summary=a.summary,
                    error_message=a.error_message,
                )
                actions.append(action_sum)
                if a.status == "Failed":
                    failed_actions.append(action_sum)

            stage_summaries.append(
                PipelineStageSummary(
                    stage_name=s.stage_name,
                    status=s.status,
                    actions=actions,
                )
            )

        if exec_res.status and exec_res.status not in {"UNKNOWN", "NOT_FOUND"}:
            last_status = exec_res.status
        elif state_res.status:
            last_status = state_res.status

        if on_update is not None:
            on_update(
                PipelineWatchUpdate(
                    pipeline_name=resolved_pipeline_name,
                    execution_id=resolved_execution_id,
                    status=last_status,
                    stages=stage_summaries,
                    elapsed_seconds=elapsed,
                )
            )

        if last_status in TERMINAL_STATUSES:
            if last_status == "Failed" and failed_actions:
                action_errs = [
                    f"Action '{fa.action_name}' failed: "
                    f"{fa.error_message or fa.summary or 'Unknown error'}"
                    for fa in failed_actions
                ]
                error_message = "; ".join(action_errs)
            break

        sleeper(interval)

    total_elapsed = time_provider() - start_time
    return PipelineWatchResult(
        workspace_dir=workspace_dir,
        customer_name=config.customer.name,
        pipeline_name=resolved_pipeline_name,
        pipeline_arn=pipeline_arn,
        execution_id=resolved_execution_id,
        status=last_status,
        stages=stage_summaries,
        failed_actions=failed_actions,
        elapsed_seconds=total_elapsed,
        error_message=error_message,
    )


__all__ = [
    "PipelineActionSummary",
    "PipelineStageSummary",
    "PipelineWatchResult",
    "PipelineWatchUpdate",
    "watch_pipeline_workflow",
]
