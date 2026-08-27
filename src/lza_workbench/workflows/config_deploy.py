"""Workflow for deploying LZA configuration (push -> start pipeline -> watch)."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.errors import LzaError
from lza_workbench.workflows.config_push import (
    ConfigPushResult,
    push_configuration_workflow,
)
from lza_workbench.workflows.pipeline_start import (
    PipelineStartResult,
    start_pipeline_workflow,
)
from lza_workbench.workflows.pipeline_watch import (
    PipelineWatchResult,
    PipelineWatchUpdate,
    watch_pipeline_workflow,
)
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context


@dataclass(frozen=True)
class ConfigDeployResult:
    """Structured result of complete configuration deployment workflow."""

    push_result: ConfigPushResult | None
    start_result: PipelineStartResult | None
    watch_result: PipelineWatchResult | None = None
    dry_run: bool = False


class ConfigDeployError(LzaError):
    """Deployment failure that retains completed workflow stages for presentation/recovery."""

    def __init__(
        self,
        message: str,
        *,
        push_result: ConfigPushResult | None = None,
        start_result: PipelineStartResult | None = None,
        watch_result: PipelineWatchResult | None = None,
    ) -> None:
        self.result = ConfigDeployResult(
            push_result=push_result,
            start_result=start_result,
            watch_result=watch_result,
            dry_run=False,
        )
        super().__init__(message)


def deploy_configuration_workflow(
    *,
    target_dir: Path | None = None,
    dry_run: bool = False,
    watch: bool = True,
    poll_interval_seconds: int | None = None,
    timeout_seconds: int | None = 7200,
    sleeper: Callable[[float], None] = time.sleep,
    time_provider: Callable[[], float] = time.time,
    on_watch_update: Callable[[PipelineWatchUpdate], None] | None = None,
) -> ConfigDeployResult:
    """Synchronize configuration to remote source, start pipeline, and watch execution."""
    context = load_workspace_context(
        target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED
    )
    try:
        aws_context = resolve_aws_execution_context(
            profile=context.config.aws.profile,
            region=context.config.aws.region,
            role_arn=context.config.aws.role_arn,
            expected_account_id=context.config.aws.account_id,
            require_identity=not dry_run,
            require_expected_account=not dry_run,
        )
    except Exception as exc:
        if isinstance(exc, LzaError):
            raise
        raise LzaError(f"AWS identity resolution failed: {exc}") from exc

    push_res: ConfigPushResult | None = None
    try:
        push_res = push_configuration_workflow(
            target_dir=target_dir,
            dry_run=dry_run,
            workspace_context=context,
            aws_context=aws_context,
        )
    except Exception as exc:
        raise ConfigDeployError(f"Configuration push failed: {exc}") from exc

    start_res: PipelineStartResult | None = None
    try:
        start_res = start_pipeline_workflow(
            target_dir=target_dir,
            pipeline_type="configuration",
            dry_run=dry_run,
            workspace_context=context,
            aws_context=aws_context,
        )
    except Exception as exc:
        raise ConfigDeployError(
            f"Configuration push succeeded, but pipeline start failed: {exc}",
            push_result=push_res,
        ) from exc

    watch_res: PipelineWatchResult | None = None
    if not dry_run and watch:
        try:
            watch_res = watch_pipeline_workflow(
                target_dir=target_dir,
                pipeline_type="configuration",
                execution_id=start_res.execution_id,
                poll_interval_seconds=poll_interval_seconds,
                timeout_seconds=timeout_seconds,
                sleeper=sleeper,
                time_provider=time_provider,
                on_update=on_watch_update,
                workspace_context=context,
                aws_context=aws_context,
            )
        except KeyboardInterrupt as exc:
            raise ConfigDeployError(
                f"Pipeline execution started with ID '{start_res.execution_id}', "
                "but monitoring was interrupted.",
                push_result=push_res,
                start_result=start_res,
            ) from exc
        except Exception as exc:
            raise ConfigDeployError(
                f"Pipeline execution started with ID '{start_res.execution_id}', "
                f"but monitoring failed: {exc}",
                push_result=push_res,
                start_result=start_res,
            ) from exc

        if watch_res.status != "Succeeded":
            raise ConfigDeployError(
                f"LZA deployment failed. Pipeline execution {watch_res.execution_id} "
                f"ended with status '{watch_res.status}'.",
                push_result=push_res,
                start_result=start_res,
                watch_result=watch_res,
            )

    return ConfigDeployResult(
        push_result=push_res,
        start_result=start_res,
        watch_result=watch_res,
        dry_run=dry_run,
    )


__all__ = ["ConfigDeployError", "ConfigDeployResult", "deploy_configuration_workflow"]
