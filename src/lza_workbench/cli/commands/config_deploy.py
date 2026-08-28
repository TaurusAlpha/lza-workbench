"""CLI command and presentation for deploying LZA configuration (push, start pipeline, watch)."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.cli import params
from lza_workbench.cli.commands.config_push import render_config_push_result
from lza_workbench.cli.commands.pipeline_start import render_pipeline_start_result
from lza_workbench.cli.commands.pipeline_watch import (
    PipelineWatchMonitor,
    render_pipeline_watch_result,
)
from lza_workbench.cli.output import (
    console,
    print_dry_run_header,
    print_section,
)
from lza_workbench.workflows.config_deploy import (
    ConfigDeployError,
    ConfigDeployResult,
    deploy_configuration_workflow,
)


def render_config_deploy_result(
    result: ConfigDeployResult,
    *,
    verbose: bool = False,
) -> None:
    """Render the full results of configuration deployment."""
    if result.dry_run:
        print_dry_run_header("lza config deploy")
        console.print("[bold]Step 1: Configuration Push (Planned)[/bold]")
        if result.push_result:
            render_config_push_result(result.push_result)
        console.print()
        console.print("[bold]Step 2: Pipeline Execution (Planned)[/bold]")
        if result.start_result:
            render_pipeline_start_result(result.start_result)
        return

    print_section(1, "Configuration Synchronization")
    if result.push_result:
        render_config_push_result(result.push_result)

    console.print()
    print_section(2, "Pipeline Execution Trigger")
    if result.start_result:
        render_pipeline_start_result(result.start_result)

    if result.watch_result is not None:
        console.print()
        print_section(3, "Pipeline Monitoring")
        render_pipeline_watch_result(result.watch_result, verbose=verbose)


def config_deploy_command(
    dry_run: params.DryRun = False,
    no_watch: params.NoWatch = False,
    verbose: params.Verbose = False,
    target_dir: Path | None = None,
) -> ConfigDeployResult:
    """Synchronize configuration to remote destination and trigger LZA pipeline execution."""
    monitor = PipelineWatchMonitor()
    try:
        result = deploy_configuration_workflow(
            target_dir=target_dir,
            dry_run=dry_run,
            watch=not no_watch,
            on_watch_update=monitor.update,
        )
    except ConfigDeployError as exc:
        render_config_deploy_result(exc.result, verbose=verbose)
        raise
    finally:
        monitor.stop()

    render_config_deploy_result(result, verbose=verbose)

    return result


__all__ = [
    "config_deploy_command",
    "render_config_deploy_result",
]
