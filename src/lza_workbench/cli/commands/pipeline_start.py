"""CLI command and presentation for starting LZA pipeline executions."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.cli import params
from lza_workbench.cli.output import (
    print_dry_run_header,
    print_info,
    print_kv,
    print_success,
)
from lza_workbench.workflows.pipeline_start import (
    PipelineStartResult,
    start_pipeline_workflow,
)


def render_pipeline_start_result(result: PipelineStartResult) -> None:
    """Render the result of starting a pipeline execution."""
    if result.dry_run:
        print_dry_run_header("lza pipeline start")
        print_kv("Workspace", result.workspace_dir)
        print_kv("Target AWS Profile", result.profile or "default")
        print_kv("Target Region", result.region)
        print_kv("Target Account", result.account_id)
        print_kv("Pipeline Name", result.pipeline_name)
        print_kv("Planned Action", "Start pipeline execution")
        return

    print_success(f"Started pipeline execution for '{result.pipeline_name}'")
    print_kv("Workspace", result.workspace_dir)
    print_kv("Pipeline ARN", result.pipeline_arn)
    print_kv("Execution ID", result.execution_id or "None", bold_value=True)
    print_info("Recorded execution ID in workspace state", dim=True)



def pipeline_start_command(
    pipeline_name: params.PipelineName = None,
    dry_run: params.DryRun = False,
    target_dir: Path | None = None,
) -> PipelineStartResult:
    """Start an LZA CodePipeline execution."""
    result = start_pipeline_workflow(
        target_dir=target_dir,
        pipeline_name=pipeline_name,
        pipeline_type="configuration",
        dry_run=dry_run,
    )
    render_pipeline_start_result(result)
    return result


__all__ = [
    "pipeline_start_command",
    "render_pipeline_start_result",
]
