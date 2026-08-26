"""CLI command and presentation for deploying LZA configuration (push, start pipeline, watch)."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.cli import params
from lza_workbench.cli.commands.config_push import render_config_push_result
from lza_workbench.cli.commands.pipeline_start import render_pipeline_start_result
from lza_workbench.cli.commands.pipeline_watch import (
    render_pipeline_watch_result,
    render_pipeline_watch_update,
)
from lza_workbench.cli.output import (
    console,
    print_dry_run_header,
    print_section,
)
from lza_workbench.errors import LzaError
from lza_workbench.workflows.config_deploy import (
    ConfigDeployResult,
    deploy_configuration_workflow,
)


def render_config_deploy_result(result: ConfigDeployResult) -> None:
    """Render the full results of configuration deployment."""
    if result.dry_run:
        print_dry_run_header("lza config deploy")
        console.print("[bold]Step 1: Configuration Push (Planned)[/bold]")
        render_config_push_result(result.push_result)
        console.print()
        console.print("[bold]Step 2: Pipeline Execution (Planned)[/bold]")
        render_pipeline_start_result(result.start_result)
        return

    print_section(1, "Configuration Synchronization")
    render_config_push_result(result.push_result)

    console.print()
    print_section(2, "Pipeline Execution Trigger")
    render_pipeline_start_result(result.start_result)

    if result.watch_result is not None:
        console.print()
        print_section(3, "Pipeline Monitoring")
        render_pipeline_watch_result(result.watch_result)


def config_deploy_command(
    dry_run: params.DryRun = False,
    no_watch: params.NoWatch = False,
    target_dir: Path | None = None,
) -> ConfigDeployResult:
    """Synchronize configuration to remote destination and trigger LZA pipeline execution."""
    result = deploy_configuration_workflow(
        target_dir=target_dir,
        dry_run=dry_run,
        watch=not no_watch,
        on_watch_update=render_pipeline_watch_update,
    )
    render_config_deploy_result(result)

    if result.watch_result and result.watch_result.status != "Succeeded":
        raise LzaError(
            f"LZA deployment failed. Pipeline execution {result.watch_result.execution_id} "
            f"ended with status '{result.watch_result.status}'."
        )

    return result


__all__ = [
    "config_deploy_command",
    "render_config_deploy_result",
]
