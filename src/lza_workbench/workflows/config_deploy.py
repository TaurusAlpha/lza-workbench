"""Workflow for deploying LZA configuration (push -> start pipeline -> watch)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.errors import LzaError
from lza_workbench.workflows.config_push import (
    ConfigPushRequest,
    ConfigPushResult,
    apply_config_push,
)
from lza_workbench.workflows.pipeline_start import (
    PipelineStartResult,
    start_pipeline_workflow,
)
from lza_workbench.workflows.pipeline_watch import (
    PipelineWatchError,
    PipelineWatchResult,
    PipelineWatchUpdate,
    require_successful_pipeline_watch,
    watch_pipeline_workflow,
)
from lza_workbench.workspace.context import WorkspaceCapability, load_workspace_context


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
    initial_delay_seconds: float = 3.0,
    timeout_seconds: int | None = 7200,
    on_watch_update: Callable[[PipelineWatchUpdate], None] | None = None,
) -> ConfigDeployResult:
    """Synchronize configuration to remote source, start pipeline, and watch execution."""
    context = load_workspace_context(
        target_dir, required_capabilities=(WorkspaceCapability.METADATA_VALID,)
    )
    try:
        aws_context = resolve_aws_execution_context(
            profile=context.config.aws.profile,
            region=context.config.aws.region,
            role_arn=context.config.aws.role_arn,
            expected_account_id=context.config.aws.account_id,
            require_identity=not dry_run,
            require_expected_account=not dry_run,
            prime_credentials=context.config.aws.prime_credentials,
        )
    except Exception as exc:
        if isinstance(exc, LzaError):
            raise
        raise LzaError(f"AWS identity resolution failed: {exc}") from exc

    push_res: ConfigPushResult | None = None
    try:
        push_res = apply_config_push(
            ConfigPushRequest(
                target_dir=target_dir,
                dry_run=dry_run,
                workspace_context=context,
                aws_context=aws_context,
            )
        )
    except LzaError as exc:
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
    except LzaError as exc:
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
                initial_delay_seconds=initial_delay_seconds,
                timeout_seconds=timeout_seconds,
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
        except LzaError as exc:
            raise ConfigDeployError(
                f"Pipeline execution started with ID '{start_res.execution_id}', "
                f"but monitoring failed: {exc}",
                push_result=push_res,
                start_result=start_res,
            ) from exc

        try:
            require_successful_pipeline_watch(watch_res)
        except PipelineWatchError as exc:
            raise ConfigDeployError(
                str(exc),
                push_result=push_res,
                start_result=start_res,
                watch_result=exc.result,
            ) from exc

    return ConfigDeployResult(
        push_result=push_res,
        start_result=start_res,
        watch_result=watch_res,
        dry_run=dry_run,
    )


__all__ = ["ConfigDeployError", "ConfigDeployResult", "deploy_configuration_workflow"]
