"""Workflow for monitoring AWS CodePipeline executions."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from lza_workbench.aws.codebuild import (
    fetch_codebuild_diagnostics,
    normalize_root_cause_and_resource,
)
from lza_workbench.aws.codepipeline import (
    get_latest_pipeline_execution_id,
    get_pipeline_execution,
    get_pipeline_state,
)
from lza_workbench.aws.context import AwsExecutionContext, resolve_aws_execution_context
from lza_workbench.errors import LzaError
from lza_workbench.pipeline.resolution import resolve_pipeline
from lza_workbench.pipeline.state import record_pipeline_watch_result
from lza_workbench.workspace.context import (
    WorkspaceContext,
    WorkspaceReadinessLevel,
    load_workspace_context,
)
from lza_workbench.workspace.state import write_workspace_state


@dataclass(frozen=True)
class PipelineActionSummary:
    """Status and error details of an individual action inside a pipeline stage."""

    action_name: str
    stage_name: str | None = None
    status: str | None = None
    summary: str | None = None
    error_message: str | None = None
    external_execution_id: str | None = None
    external_execution_url: str | None = None
    diagnostic_details: list[str] = field(default_factory=list)
    raw_diagnostic_details: list[str] = field(default_factory=list)
    failed_resource: str | None = None


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
    elapsed_seconds: float | None = None
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
    workspace_context: WorkspaceContext | None = None,
    aws_context: AwsExecutionContext | None = None,
) -> PipelineWatchResult:
    """Monitor a CodePipeline execution until completion or timeout."""
    ctx = workspace_context or load_workspace_context(
        target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED
    )
    workspace_dir, config, state = ctx.workspace_dir, ctx.config, ctx.state

    pipeline = resolve_pipeline(config, pipeline_type=pipeline_type, pipeline_name=pipeline_name)
    resolved_pipeline_name = pipeline.name

    profile = config.aws.profile or ""
    resolved_aws_context = aws_context or resolve_aws_execution_context(
        profile=profile,
        region=config.aws.region,
        role_arn=config.aws.role_arn,
        expected_account_id=config.aws.account_id,
        require_identity=True,
        require_expected_account=True,
    )

    region = resolved_aws_context.region
    account_id = (
        resolved_aws_context.identity["account"]
        if resolved_aws_context.identity
        else "UNKNOWN_ACCOUNT"
    )
    pipeline_arn = pipeline.arn(region=region, account_id=account_id)
    client = resolved_aws_context.factory.get_client("codepipeline")

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
    last_exec_res = None

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
        last_exec_res = exec_res

        state_res = get_pipeline_state(
            client=client,
            pipeline_name=resolved_pipeline_name,
        )

        stage_summaries = []
        failed_actions = []
        for s in state_res.stage_states:
            if s.execution_id and s.execution_id != resolved_execution_id:
                continue
            actions: list[PipelineActionSummary] = []
            for a in s.actions:
                if a.execution_id and a.execution_id != resolved_execution_id:
                    continue
                action_sum = PipelineActionSummary(
                    action_name=a.action_name,
                    stage_name=s.stage_name,
                    status=a.status,
                    summary=a.summary,
                    error_message=a.error_message,
                    external_execution_id=a.external_execution_id,
                    external_execution_url=a.external_execution_url,
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
                enriched_failed: list[PipelineActionSummary] = []
                for fa in failed_actions:
                    diagnostics: list[str] = []
                    if fa.external_execution_id:
                        diagnostics = fetch_codebuild_diagnostics(
                            factory=resolved_aws_context.factory,
                            build_id=fa.external_execution_id,
                        )

                    raw_diags = list(diagnostics)
                    norm_diags: list[str] = []
                    detected_resource: str | None = None

                    if diagnostics:
                        for d in diagnostics:
                            norm_err, res = normalize_root_cause_and_resource(d)
                            if res and not detected_resource:
                                detected_resource = res
                            if norm_err and norm_err not in norm_diags:
                                norm_diags.append(norm_err)
                    elif fa.error_message or fa.summary:
                        raw_msg = str(fa.error_message or fa.summary)
                        raw_diags = [raw_msg]
                        norm_err, res = normalize_root_cause_and_resource(raw_msg)
                        if res:
                            detected_resource = res
                        norm_diags = [norm_err] if norm_err else [raw_msg]

                    fa_enriched = PipelineActionSummary(
                        action_name=fa.action_name,
                        stage_name=fa.stage_name,
                        status=fa.status,
                        summary=fa.summary,
                        error_message=fa.error_message,
                        external_execution_id=fa.external_execution_id,
                        external_execution_url=fa.external_execution_url,
                        diagnostic_details=norm_diags,
                        raw_diagnostic_details=raw_diags,
                        failed_resource=detected_resource,
                    )
                    enriched_failed.append(fa_enriched)

                failed_actions = enriched_failed

                action_errs = []
                for fa in failed_actions:
                    stage_prefix = (
                        f"Stage '{fa.stage_name}', action" if fa.stage_name else "Action"
                    )
                    if fa.diagnostic_details:
                        diag_text = "\n  - ".join(fa.diagnostic_details)
                        action_errs.append(
                            f"{stage_prefix} '{fa.action_name}' failed:\n  - {diag_text}"
                        )
                    else:
                        err_text = fa.error_message or fa.summary or "Unknown error"
                        action_errs.append(f"{stage_prefix} '{fa.action_name}' failed: {err_text}")
                error_message = "\n".join(action_errs)
            break

        sleeper(interval)

    total_elapsed: float | None = None
    if (
        last_exec_res
        and last_exec_res.duration_seconds is not None
        and last_exec_res.duration_seconds > 0
    ):
        total_elapsed = last_exec_res.duration_seconds
    else:
        live_dur = time_provider() - start_time
        if live_dur >= 1.0:
            total_elapsed = live_dur


    watch_result = PipelineWatchResult(
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

    if state is not None:
        record_pipeline_watch_result(
            state,
            execution_id=resolved_execution_id,
            status=last_status,
            stages=stage_summaries,
            failed_actions=failed_actions,
            error_message=error_message,
            pipeline_type=pipeline_type,
        )
        write_workspace_state(workspace_dir, state)

    return watch_result


__all__ = [
    "PipelineActionSummary",
    "PipelineStageSummary",
    "PipelineWatchResult",
    "PipelineWatchUpdate",
    "watch_pipeline_workflow",
]

