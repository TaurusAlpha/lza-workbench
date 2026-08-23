"""CLI command and presentation for monitoring LZA pipeline executions."""

from __future__ import annotations

from pathlib import Path

from rich.table import Table

from lza_workbench.cli import params
from lza_workbench.cli.output import (
    console,
    print_info,
    print_kv,
    print_notice,
    print_section,
    print_success,
)
from lza_workbench.errors import LzaError
from lza_workbench.workflows.pipeline_watch import (
    PipelineWatchResult,
    PipelineWatchUpdate,
    watch_pipeline_workflow,
)


def _status_color(status: str | None) -> str:
    if not status:
        return "dim"
    if status == "Succeeded":
        return "green"
    if status == "Failed":
        return "bold red"
    if status in {"InProgress", "Building"}:
        return "yellow"
    if status in {"Cancelled", "Stopped"}:
        return "magenta"
    return "white"


def render_pipeline_watch_update(update: PipelineWatchUpdate) -> None:
    """Render intermediate update during pipeline polling."""
    elapsed_str = f"{int(update.elapsed_seconds)}s"
    color = _status_color(update.status)
    status_tag = f"[{color}]{update.status}[/{color}]"
    print_info(
        f"Pipeline {status_tag} - Execution: {update.execution_id} ({elapsed_str})",
        dim=True,
    )


def render_pipeline_watch_result(result: PipelineWatchResult) -> None:
    """Render the final summary table and outcome of a pipeline watch."""
    console.print()
    print_section(1, "Pipeline Execution Summary")
    print_kv("Pipeline Name", result.pipeline_name, bold_value=True)
    print_kv("Execution ID", result.execution_id, bold_value=True)
    print_kv("Duration", f"{int(result.elapsed_seconds)} seconds")
    color = _status_color(result.status)
    print_kv("Final Status", f"[{color}]{result.status}[/{color}]", bold_value=True)

    if result.stages:
        console.print()
        table = Table(title="Stage & Action Breakdown", show_header=True)
        table.add_column("Stage", style="bold cyan")
        table.add_column("Action", style="white")
        table.add_column("Status", style="bold")
        table.add_column("Details", style="dim")

        for stage in result.stages:
            stage_status_col = _status_color(stage.status)
            if not stage.actions:
                table.add_row(
                    stage.stage_name,
                    "-",
                    f"[{stage_status_col}]{stage.status or 'NotStarted'}[/{stage_status_col}]",
                    "",
                )
            else:
                for idx, action in enumerate(stage.actions):
                    act_color = _status_color(action.status)
                    details = action.error_message or action.summary or ""
                    table.add_row(
                        stage.stage_name if idx == 0 else "",
                        action.action_name,
                        f"[{act_color}]{action.status or 'Pending'}[/{act_color}]",
                        details,
                    )
        console.print(table)

    if result.status == "Succeeded":
        print_success(f"Pipeline '{result.pipeline_name}' execution completed successfully.")
    elif result.status == "Failed":
        print_notice(f"Pipeline '{result.pipeline_name}' execution failed.")
        if result.failed_actions:
            console.print("[bold red]Action Failures & Diagnostics:[/bold red]")
            for fa in result.failed_actions:
                console.print(f"  ❌ [bold]{fa.action_name}[/bold]")
                if fa.diagnostic_details:
                    for diag in fa.diagnostic_details:
                        console.print(f"     [red]{diag}[/red]")
                elif fa.error_message or fa.summary:
                    console.print(f"     [red]{fa.error_message or fa.summary}[/red]")
                if fa.external_execution_url:
                    console.print(f"     [dim]Build Console:[/dim] {fa.external_execution_url}")
        elif result.error_message:
            console.print(f"[bold red]Failure details:[/bold red] {result.error_message}")
    else:
        print_notice(
            f"Pipeline '{result.pipeline_name}' execution finished with status: {result.status}"
        )


def pipeline_watch_command(
    pipeline_name: params.PipelineName = None,
    execution_id: params.ExecutionId = None,
    poll_interval: params.PollInterval = None,
    target_dir: Path | None = None,
) -> PipelineWatchResult:
    """Monitor an existing LZA CodePipeline execution."""
    result = watch_pipeline_workflow(
        target_dir=target_dir,
        pipeline_name=pipeline_name,
        pipeline_type="configuration",
        execution_id=execution_id,
        poll_interval_seconds=poll_interval,
        on_update=render_pipeline_watch_update,
    )
    render_pipeline_watch_result(result)
    if result.status != "Succeeded":
        raise LzaError(
            f"Pipeline execution {result.execution_id} ended with status '{result.status}'."
        )
    return result


__all__ = [
    "pipeline_watch_command",
    "render_pipeline_watch_result",
    "render_pipeline_watch_update",
]
