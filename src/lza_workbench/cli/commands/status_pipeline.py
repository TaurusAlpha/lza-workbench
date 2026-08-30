"""CLI command and presentation for pipeline status."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lza_workbench.cli.output import (
    console,
    format_status,
    print_info,
    print_kv,
    print_notice,
    print_section,
    render_workspace_header,
)
from lza_workbench.workflows.status_pipeline import (
    PipelineStatusResult,
    get_pipeline_status_workflow,
)


def _render_pipeline_detail(
    name: str,
    status: str | None,
    error: str | None,
    latest_exec_id: str | None,
    stage_states: list[Any] | None = None,
) -> None:
    print_kv("Pipeline Name", name, bold_value=True)
    print_kv("Pipeline Status", format_status(status))
    if latest_exec_id:
        print_kv("Latest Execution ID", latest_exec_id, style="dim")
    if stage_states:
        stage_parts = []
        for s in stage_states:
            s_status = getattr(s, "status", None) or "Unknown"
            s_name = getattr(s, "stage_name", "Unknown")
            stage_parts.append(f"{s_name} ({format_status(s_status)})")
        print_kv("Pipeline Stages", " -> ".join(stage_parts))
    if error:
        print_notice(f"Pipeline Query Notice: {error}")


def render_pipeline_status(result: PipelineStatusResult, *, has_state: bool) -> None:
    """Render prepared pipeline status without AWS calls or workspace reads."""
    render_workspace_header(
        "LZA Pipeline Status",
        customer_name=result.customer_name,
        workspace_dir=result.workspace_dir,
        profile=result.profile,
        region=result.region,
        aws_identity=result.aws_identity,
        aws_error=result.aws_error,
    )

    # Section 1: Installer Pipeline
    console.print()
    print_section(1, "Installer Pipeline")
    _render_pipeline_detail(
        result.installer_pipeline_name,
        result.installer_pipeline_state.status,
        result.installer_pipeline_state.error,
        result.installer_pipeline_state.latest_execution_id,
        result.installer_pipeline_state.stage_states,
    )

    # Section 2: Configuration Pipeline
    console.print()
    print_section(2, "Configuration Pipeline")
    _render_pipeline_detail(
        result.config_pipeline_name,
        result.config_pipeline_state.status,
        result.config_pipeline_state.error,
        result.config_pipeline_state.latest_execution_id,
        result.config_pipeline_state.stage_states,
    )

    # Section 3: Execution History
    console.print()
    print_section(3, "Execution History")
    if has_state:
        print_kv(
            "Recorded Installer Execution ID",
            result.installer_execution_id or "None recorded",
        )
        print_kv(
            "Recorded Configuration Execution ID",
            result.config_execution_id or "None recorded",
        )
    else:
        print_info("No recorded workspace state found.", dim=True)


def status_pipeline_command(
    target_dir: Path | None = None,
) -> None:
    """Query AWS CodePipeline state and render workspace execution metadata."""
    result = get_pipeline_status_workflow(target_dir=target_dir)
    render_pipeline_status(result, has_state=result.has_state)


__all__ = [
    "render_pipeline_status",
    "status_pipeline_command",
]

