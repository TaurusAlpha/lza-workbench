"""Workflow for deploying LZA configuration (push -> start pipeline -> watch)."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

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


@dataclass(frozen=True)
class ConfigDeployResult:
    """Structured result of complete configuration deployment workflow."""

    push_result: ConfigPushResult
    start_result: PipelineStartResult
    watch_result: PipelineWatchResult | None = None
    dry_run: bool = False


def deploy_configuration_workflow(
    *,
    target_dir: Path | None = None,
    dry_run: bool = False,
    watch: bool = True,
    poll_interval_seconds: int | None = None,
    timeout_seconds: int | None = 7200,
    bucket_resolver: Callable[[], str] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    time_provider: Callable[[], float] = time.time,
    on_watch_update: Callable[[PipelineWatchUpdate], None] | None = None,
) -> ConfigDeployResult:
    """Synchronize configuration to remote source, start pipeline, and watch execution."""
    push_res = push_configuration_workflow(
        target_dir=target_dir,
        dry_run=dry_run,
        bucket_resolver=bucket_resolver,
    )

    start_res = start_pipeline_workflow(
        target_dir=target_dir,
        pipeline_type="configuration",
        dry_run=dry_run,
    )

    watch_res: PipelineWatchResult | None = None
    if not dry_run and watch:
        watch_res = watch_pipeline_workflow(
            target_dir=target_dir,
            pipeline_type="configuration",
            execution_id=start_res.execution_id,
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=timeout_seconds,
            sleeper=sleeper,
            time_provider=time_provider,
            on_update=on_watch_update,
        )

    return ConfigDeployResult(
        push_result=push_res,
        start_result=start_res,
        watch_result=watch_res,
        dry_run=dry_run,
    )


__all__ = ["ConfigDeployResult", "deploy_configuration_workflow"]
