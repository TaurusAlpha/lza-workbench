"""Workflow for monitoring AWS CodePipeline executions."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lza_workbench.errors import LzaError
from lza_workbench.infrastructure.aws.codepipeline import (
    get_latest_pipeline_execution_id,
)
from lza_workbench.infrastructure.aws.session import (
    AwsExecutionContext,
    resolve_aws_execution_context,
)
from lza_workbench.pipeline.failures import (
    PipelineActionFailure,
    collect_pipeline_action_failures,
    fetch_codebuild_diagnostics,
)
from lza_workbench.pipeline.model import PipelineStageState
from lza_workbench.pipeline.observation import observe_pipeline_execution
from lza_workbench.pipeline.resolution import resolve_pipeline
from lza_workbench.pipeline.state import record_pipeline_watch_result
from lza_workbench.workspace.context import (
    WorkspaceContext,
    load_workspace_context,
)
from lza_workbench.workspace.persistence import update_workspace_state
from lza_workbench.workspace.schema import CustomerEnvironmentTarget, WorkspaceState
from lza_workbench.workspace.validation import WorkspaceCapability


@dataclass(frozen=True)
class PipelineWatchUpdate:
    """Progress update emitted during pipeline polling."""

    pipeline_name: str
    execution_id: str
    status: str
    stages: list[PipelineStageState]
    elapsed_seconds: float


@dataclass(frozen=True)
class PipelineWatchResult:
    workspace_dir: Path | None
    customer_name: str
    pipeline_name: str
    pipeline_arn: str
    execution_id: str
    status: str
    stages: list[PipelineStageState]
    failed_actions: list[PipelineActionFailure]
    elapsed_seconds: float | None = None
    error_message: str | None = None


TERMINAL_STATUSES = {"Succeeded", "Failed", "Cancelled", "Stopped", "Superseded"}


class PipelineWatchError(LzaError):
    """Unsuccessful terminal pipeline result retained for interface rendering."""

    def __init__(self, result: PipelineWatchResult) -> None:
        self.result = result
        super().__init__(
            f"Pipeline execution '{result.execution_id}' ended with status '{result.status}'."
        )


def require_successful_pipeline_watch(result: PipelineWatchResult) -> None:
    """Raise an application error when a watched execution did not succeed."""
    if result.status != "Succeeded":
        raise PipelineWatchError(result)


def _resolve_watch_execution_id(
    *,
    client: Any,
    state: Any,
    pipeline_type: str,
    pipeline_name: str,
    execution_id: str | None,
) -> str:
    if execution_id:
        return execution_id

    if state is not None:
        track = state.pipelines.track(pipeline_type)
        recorded_execution_id = track.execution_id_for_pipeline(pipeline_name)
        if recorded_execution_id:
            return recorded_execution_id

    latest = get_latest_pipeline_execution_id(
        client=client,
        pipeline_name=pipeline_name,
    )
    if latest:
        return latest

    raise LzaError(
        f"No execution found to watch for pipeline '{pipeline_name}'. "
        "Start a pipeline execution before watching."
    )


def _resolve_terminal_failures(
    *,
    stage_summaries: list[PipelineStageState],
    last_status: str,
    aws_context: AwsExecutionContext,
) -> tuple[list[PipelineActionFailure], str | None]:
    has_failed_action = any(
        action.status == "Failed" for stage in stage_summaries for action in stage.actions
    )
    failed_actions: list[PipelineActionFailure] = []
    if has_failed_action:
        codebuild_client = aws_context.factory.get_client("codebuild")
        logs_client = aws_context.factory.get_client("logs")
        failed_actions = collect_pipeline_action_failures(
            stage_summaries,
            fetch_diagnostics=lambda build_id, cb=codebuild_client, lc=logs_client: (
                fetch_codebuild_diagnostics(
                    codebuild_client=cb,
                    logs_client=lc,
                    build_id=build_id,
                )
            ),
        )

    error_message = None
    if last_status == "Failed" and failed_actions:
        action_errs = []
        for fa in failed_actions:
            stage_prefix = f"Stage '{fa.stage_name}', action" if fa.stage_name else "Action"
            if fa.diagnostic_details:
                diag_text = "\n  - ".join(fa.diagnostic_details)
                action_errs.append(f"{stage_prefix} '{fa.action_name}' failed:\n  - {diag_text}")
            else:
                err_text = fa.error_message or fa.summary or "Unknown error"
                action_errs.append(f"{stage_prefix} '{fa.action_name}' failed: {err_text}")
        error_message = "\n".join(action_errs)

    return failed_actions, error_message


def _calculate_watch_elapsed(
    *,
    last_snapshot: Any,
    start_time: float,
) -> float | None:
    if (
        last_snapshot
        and last_snapshot.duration_seconds is not None
        and last_snapshot.duration_seconds > 0
    ):
        return float(last_snapshot.duration_seconds)

    live_dur = time.time() - start_time
    if live_dur >= 1.0:
        return live_dur
    return None


def watch_pipeline_workflow(
    *,
    target_dir: Path | None = None,
    pipeline_name: str | None = None,
    pipeline_type: str = "configuration",
    accelerator_prefix: str = "AWSAccelerator",
    customer_name: str | None = None,
    execution_id: str | None = None,
    poll_interval_seconds: int | None = None,
    initial_delay_seconds: float = 3.0,
    timeout_seconds: int | None = 7200,
    on_update: Callable[[PipelineWatchUpdate], None] | None = None,
    environment_target: CustomerEnvironmentTarget | None = None,
    workspace_context: WorkspaceContext | None = None,
    aws_context: AwsExecutionContext | None = None,
) -> PipelineWatchResult:
    """Monitor a CodePipeline execution until completion or timeout."""
    if poll_interval_seconds is not None and poll_interval_seconds <= 0:
        raise LzaError("Pipeline poll interval must be greater than zero seconds.")
    if initial_delay_seconds < 0:
        raise LzaError("Pipeline initial delay must be greater than or equal to zero seconds.")

    ctx = workspace_context
    if ctx is None and (target_dir is not None or aws_context is None):
        ctx = load_workspace_context(
            target_dir, required_capabilities=(WorkspaceCapability.METADATA_VALID,)
        )

    workspace_dir = ctx.workspace_dir if ctx is not None else None
    config = ctx.config if ctx is not None else None
    state = ctx.state if ctx is not None else None
    env_target = environment_target or (config.environment_target if config is not None else None)

    pipeline = resolve_pipeline(
        env_target,
        pipeline_type=pipeline_type,
        pipeline_name=pipeline_name,
        accelerator_prefix=accelerator_prefix,
    )
    resolved_pipeline_name = pipeline.name
    resolved_customer_name = (
        customer_name
        if customer_name is not None
        else (env_target.customer.name if env_target is not None else "")
    )
    expected_account_id = env_target.account_id if env_target is not None else None

    if aws_context is not None:
        resolved_aws_context = aws_context
        if expected_account_id is not None:
            resolved_aws_context.require_live(expected_account_id=expected_account_id)
    elif config is not None:
        profile = config.aws.profile or ""
        resolved_aws_context = resolve_aws_execution_context(
            profile=profile,
            region=config.aws.region,
            role_arn=config.aws.role_arn,
            expected_account_id=expected_account_id,
            require_identity=True,
            require_expected_account=True,
            prime_credentials=config.aws.prime_credentials,
        )
    else:
        raise LzaError("Pipeline watch requires an AWS execution context or workspace.")

    region = resolved_aws_context.region
    account_id = (
        resolved_aws_context.identity["account"]
        if resolved_aws_context.identity
        else "UNKNOWN_ACCOUNT"
    )
    pipeline_arn = pipeline.arn(region=region, account_id=account_id)
    client = resolved_aws_context.factory.get_client("codepipeline")

    resolved_execution_id = _resolve_watch_execution_id(
        client=client,
        state=state,
        pipeline_type=pipeline_type,
        pipeline_name=resolved_pipeline_name,
        execution_id=execution_id,
    )

    if initial_delay_seconds > 0:
        time.sleep(initial_delay_seconds)

    interval = poll_interval_seconds
    if interval is None:
        interval = (
            config.pipelines.configuration.poll_interval_seconds
            if config is not None
            else 15
        ) or 15

    start_time = time.time()
    last_status = "InProgress"
    stage_summaries: list[PipelineStageState] = []
    failed_actions: list[PipelineActionFailure] = []
    error_message: str | None = None
    last_snapshot = None
    not_found_attempts = 0
    max_not_found_attempts = 3

    while True:
        elapsed = time.time() - start_time
        if timeout_seconds and elapsed > timeout_seconds:
            last_status = "TimedOut"
            error_message = f"Watch timed out after {int(elapsed)} seconds."
            break

        snapshot = observe_pipeline_execution(
            client=client,
            pipeline_name=resolved_pipeline_name,
            execution_id=resolved_execution_id,
        )
        last_snapshot = snapshot

        if snapshot.status == "NOT_FOUND":
            not_found_attempts += 1
            if not_found_attempts < max_not_found_attempts:
                time.sleep(interval)
                continue
            raise LzaError(
                f"Pipeline execution '{resolved_execution_id}' was not found for "
                f"pipeline '{resolved_pipeline_name}'."
            )

        stage_summaries = snapshot.stages

        if snapshot.status and snapshot.status not in {"UNKNOWN", "NOT_FOUND"}:
            last_status = snapshot.status

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
            failed_actions, error_message = _resolve_terminal_failures(
                stage_summaries=stage_summaries,
                last_status=last_status,
                aws_context=resolved_aws_context,
            )
            break

        time.sleep(interval)

    total_elapsed = _calculate_watch_elapsed(
        last_snapshot=last_snapshot,
        start_time=start_time,
    )

    watch_result = PipelineWatchResult(
        workspace_dir=workspace_dir,
        customer_name=resolved_customer_name,
        pipeline_name=resolved_pipeline_name,
        pipeline_arn=pipeline_arn,
        execution_id=resolved_execution_id,
        status=last_status,
        stages=stage_summaries,
        failed_actions=failed_actions,
        elapsed_seconds=total_elapsed,
        error_message=error_message,
    )

    if state is not None and workspace_dir is not None:
        def _record_watch(current: WorkspaceState) -> None:
            record_pipeline_watch_result(
                current,
                execution_id=resolved_execution_id,
                pipeline_name=resolved_pipeline_name,
                status=last_status,
                stages=stage_summaries,
                failed_actions=failed_actions,
                error_message=error_message,
                pipeline_type=pipeline_type,
                observed_pipeline_status=(last_snapshot.status if last_snapshot else None),
            )

        _record_watch(state)
        update_workspace_state(workspace_dir, _record_watch)

    return watch_result


__all__ = [
    "PipelineWatchError",
    "PipelineWatchResult",
    "PipelineWatchUpdate",
    "require_successful_pipeline_watch",
    "watch_pipeline_workflow",
]
