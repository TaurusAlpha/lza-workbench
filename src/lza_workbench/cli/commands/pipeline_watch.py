"""CLI command and presentation for monitoring LZA pipeline executions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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


class PipelineWatchMonitor:
    """Manages live updating status display during pipeline polling."""

    def __init__(self) -> None:
        self._status_ctx: Any | None = None
        self._live_status: Any | None = None

    def update(self, update: PipelineWatchUpdate) -> None:
        """Update live status display with current progress."""
        if self._live_status is None:
            self._status_ctx = console.status(
                "[bold blue]Monitoring pipeline execution...[/bold blue]"
            )
            self._live_status = self._status_ctx.__enter__()

        elapsed_str = f"{int(update.elapsed_seconds)}s"
        color = _status_color(update.status)
        status_tag = f"[{color}]{update.status}[/{color}]"

        active_stage = None
        for s in update.stages:
            if s.status in {"InProgress", "Building"}:
                active_stage = s.stage_name
                break

        stage_info = f" | Stage: [cyan]{active_stage}[/cyan]" if active_stage else ""
        if self._live_status:
            self._live_status.update(
                f"Pipeline {status_tag} - Execution: {update.execution_id}{stage_info} ({elapsed_str})"
            )

    def stop(self) -> None:
        """Clean up live status display."""
        if self._status_ctx is not None:
            try:
                self._status_ctx.__exit__(None, None, None)
            finally:
                self._status_ctx = None
                self._live_status = None


def render_pipeline_watch_update(update: PipelineWatchUpdate) -> None:
    """Render single update line (for fallback / test rendering)."""
    elapsed_str = f"{int(update.elapsed_seconds)}s"
    color = _status_color(update.status)
    status_tag = f"[{color}]{update.status}[/{color}]"
    print_info(
        f"Pipeline {status_tag} - Execution: {update.execution_id} ({elapsed_str})",
        dim=True,
    )


def _should_include_stage(
    stage_status: str | None,
    actions: list[Any],
    *,
    is_failed: bool,
    verbose: bool,
) -> bool:
    """Determine whether a stage should be shown in the summary table."""
    if verbose:
        return True
    if not is_failed:
        return True
    # In concise failure mode, omit stages that were never executed
    if stage_status in {"Succeeded", "Failed", "InProgress", "Cancelled", "Stopped"}:
        return True
    return any(
        getattr(a, "status", None) in {"Succeeded", "Failed", "InProgress", "Cancelled", "Stopped"}
        for a in actions
    )


def render_pipeline_watch_result(
    result: PipelineWatchResult,
    *,
    verbose: bool = False,
) -> None:
    """Render the final summary table and outcome of a pipeline watch."""
    console.print()
    print_section(1, "Pipeline Execution Summary")
    print_kv("Pipeline Name", result.pipeline_name, bold_value=True)
    print_kv("Execution ID", result.execution_id, bold_value=True)
    print_kv("Duration", f"{int(result.elapsed_seconds)} seconds")
    color = _status_color(result.status)
    print_kv("Final Status", f"[{color}]{result.status}[/{color}]", bold_value=True)

    is_failed = result.status == "Failed"

    if result.stages:
        # Filter stages if concise mode after failure
        visible_stages = [
            s
            for s in result.stages
            if _should_include_stage(s.status, s.actions, is_failed=is_failed, verbose=verbose)
        ]

        if visible_stages:
            console.print()
            table = Table(title="Stage & Action Breakdown", show_header=True)
            table.add_column("Stage", style="bold cyan")
            table.add_column("Action", style="white")
            table.add_column("Status", style="bold")
            table.add_column("Details", style="dim")

            for stage in visible_stages:
                stage_status_col = _status_color(stage.status)
                if not stage.actions:
                    table.add_row(
                        stage.stage_name,
                        "-",
                        f"[{stage_status_col}]{stage.status or 'NotStarted'}[/{stage_status_col}]",
                        "",
                    )
                else:
                    visible_actions = (
                        stage.actions
                        if verbose or not is_failed
                        else [
                            a
                            for a in stage.actions
                            if a.status
                            in {
                                "Succeeded",
                                "Failed",
                                "InProgress",
                                "Cancelled",
                                "Stopped",
                            }
                            or a.error_message
                            or a.summary
                        ]
                    )
                    if not visible_actions:
                        visible_actions = stage.actions

                    for idx, action in enumerate(visible_actions):
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
            console.print()
            console.print("[bold red]Action Failures & Root Cause Diagnostics:[/bold red]")
            for fa in result.failed_actions:
                stage_prefix = (
                    f"Stage: [bold cyan]{fa.stage_name}[/bold cyan] > " if fa.stage_name else ""
                )
                console.print(f"  ❌ {stage_prefix}Action: [bold]{fa.action_name}[/bold]")
                if fa.diagnostic_details:
                    for diag in fa.diagnostic_details:
                        console.print(f"     [red]{diag}[/red]")
                elif fa.error_message or fa.summary:
                    console.print(f"     [red]{fa.error_message or fa.summary}[/red]")
                if verbose and fa.raw_diagnostic_details:
                    console.print("     [dim]Raw Diagnostics:[/dim]")
                    for raw in fa.raw_diagnostic_details:
                        console.print(f"       [dim]{raw}[/dim]")
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
    verbose: params.Verbose = False,
    target_dir: Path | None = None,
) -> PipelineWatchResult:
    """Monitor an existing LZA CodePipeline execution."""
    monitor = PipelineWatchMonitor()
    try:
        result = watch_pipeline_workflow(
            target_dir=target_dir,
            pipeline_name=pipeline_name,
            pipeline_type="configuration",
            execution_id=execution_id,
            poll_interval_seconds=poll_interval,
            on_update=monitor.update,
        )
    finally:
        monitor.stop()

    render_pipeline_watch_result(result, verbose=verbose)
    if result.status != "Succeeded":
        raise LzaError(
            f"Pipeline execution {result.execution_id} ended with status '{result.status}'."
        )
    return result


__all__ = [
    "PipelineWatchMonitor",
    "pipeline_watch_command",
    "render_pipeline_watch_result",
    "render_pipeline_watch_update",
]
