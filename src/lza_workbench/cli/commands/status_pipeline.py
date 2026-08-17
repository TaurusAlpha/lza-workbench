"""CLI command and presentation for pipeline status."""

from __future__ import annotations

from pathlib import Path

from rich.panel import Panel

from lza_workbench.cli.output import (
    console,
    print_info,
    print_kv,
    print_notice,
    print_section,
)
from lza_workbench.workflows.status_pipeline import (
    PipelineStatusResult,
    get_pipeline_status_workflow,
)


def render_pipeline_status(result: PipelineStatusResult, *, has_state: bool) -> None:
    """Render prepared pipeline status without AWS calls or workspace reads."""
    console.print(
        Panel(
            f"[bold cyan]LZA Pipeline Status - {result.customer_name}[/bold cyan]",
            expand=False,
        )
    )

    print_kv("Workspace", result.workspace_dir, bold_value=True)
    print_kv("AWS Profile", result.profile or "Not specified", bold_value=True)
    print_kv("AWS Region", result.region, bold_value=True)

    if result.aws_identity:
        print_kv("AWS Account ID", result.aws_identity["account"], style="green")
    elif result.aws_error:
        print_notice(f"AWS Access Notice: {result.aws_error}")

    # Section 1: Installer Pipeline
    console.print()
    print_section(1, "Installer Pipeline")
    print_kv("Pipeline Name", result.installer_pipeline_name, bold_value=True)
    print_kv("Pipeline ARN", result.installer_pipeline_arn, style="dim")

    # Section 2: Configuration Pipeline
    console.print()
    print_section(2, "Configuration Pipeline")
    print_kv("Pipeline Name", result.config_pipeline_name, bold_value=True)
    print_kv("Pipeline ARN", result.config_pipeline_arn, style="dim")

    # Section 3: Execution Metadata
    console.print()
    print_section(3, "Execution History Metadata (.lza/state.json)")
    if has_state:
        print_kv("Last Installer Execution ID", result.installer_execution_id or "None recorded")
        print_kv("Last Configuration Execution ID", result.config_execution_id or "None recorded")
    else:
        print_info("No local state file found (.lza/state.json).", dim=True)


def status_pipeline_command(
    target_dir: Path | None = None,
) -> None:
    """Query AWS CodePipeline state for current workspace pipelines."""
    result = get_pipeline_status_workflow(target_dir=target_dir)
    render_pipeline_status(result, has_state=result.has_state)
