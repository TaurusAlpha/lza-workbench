"""CLI command and presentation for monitoring LZA pipeline executions."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from rich.table import Table

from lza_workbench.cli import params
from lza_workbench.cli.output import (
    console,
    format_status,
    print_info,
    print_kv,
    print_notice,
    print_section,
    print_success,
    render_failure_section,
)
from lza_workbench.workflows.pipeline_watch import (
    PipelineActionSummary,
    PipelineWatchResult,
    PipelineWatchUpdate,
    require_successful_pipeline_watch,
    watch_pipeline_workflow,
)


def _format_duration(seconds: float | None) -> str | None:
    """Format duration in seconds into human readable string (e.g. 2m 31s or 45s)."""
    if seconds is None or seconds <= 0:
        return None
    total_secs = int(round(seconds))
    if total_secs < 60:
        return f"{total_secs}s"
    mins = total_secs // 60
    rem_secs = total_secs % 60
    if rem_secs > 0:
        return f"{mins}m {rem_secs}s"
    return f"{mins}m"


def _format_action_table_detail(action: PipelineActionSummary) -> str:
    """Format concise action status detail for breakdown table without buildspec dumps."""
    if action.status != "Failed":
        return ""

    msg = action.error_message or action.summary or ""
    if not msg:
        return ""

    # Check for exit status / code
    exit_match = re.search(r"exit (?:status|code)\s+(\d+)", msg, flags=re.IGNORECASE)
    if exit_match:
        code = exit_match.group(1)
        phase_match = re.search(r"\b([A-Z_]+)\s+phase\b", msg, flags=re.IGNORECASE)
        phase = phase_match.group(1).upper() if phase_match else "BUILD"
        return f"CodeBuild {phase} phase failed (exit status {code})"

    if "COMMAND_EXECUTION_ERROR" in msg:
        return "CodeBuild BUILD phase failed"

    # Allow concise provider messages without raw shell commands or multi-line dumps
    if (
        len(msg) < 60
        and "\n" not in msg
        and "yarn" not in msg.lower()
        and "npm" not in msg.lower()
        and "ts-node" not in msg.lower()
    ):
        return msg.strip()

    return ""


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
        status_tag = format_status(update.status)

        active_stage = None
        for s in update.stages:
            if s.status in {"InProgress", "Building"}:
                active_stage = s.stage_name
                break

        stage_info = f" | Stage: [cyan]{active_stage}[/cyan]" if active_stage else ""
        if self._live_status:
            msg = (
                f"Pipeline {status_tag} - Execution: {update.execution_id}"
                f"{stage_info} ({elapsed_str})"
            )
            self._live_status.update(msg)

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
    status_tag = format_status(update.status)
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
    start_section_number: int = 1,
) -> None:
    """Render the final summary table and outcome of a pipeline watch."""
    console.print()
    section_title = (
        "Pipeline Execution Summary" if start_section_number == 1 else "Pipeline Monitoring"
    )
    print_section(start_section_number, section_title)
    print_kv("Pipeline Name", result.pipeline_name, bold_value=True)
    print_kv("Execution ID", result.execution_id, bold_value=True)
    dur_str = _format_duration(result.elapsed_seconds)
    if dur_str:
        print_kv("Duration", dur_str)
    print_kv("Final Status", format_status(result.status), bold_value=True)

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
                if not stage.actions:
                    table.add_row(
                        stage.stage_name,
                        "-",
                        format_status(stage.status or "NotStarted"),
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
                        details = _format_action_table_detail(action)
                        table.add_row(
                            stage.stage_name if idx == 0 else "",
                            action.action_name,
                            format_status(action.status or "Pending"),
                            details,
                        )
            console.print(table)

    if result.status == "Succeeded":
        print_success(f"Pipeline '{result.pipeline_name}' execution completed successfully.")
    elif result.status == "Failed":
        render_failure_section(
            start_section_number + 1,
            result.failed_actions,
            result.error_message,
            verbose=verbose,
        )
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
    require_successful_pipeline_watch(result)
    return result


__all__ = [
    "PipelineWatchMonitor",
    "pipeline_watch_command",
    "render_pipeline_watch_result",
    "render_pipeline_watch_update",
]
