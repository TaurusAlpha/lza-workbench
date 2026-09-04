"""CLI command and presentation for root workspace status."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.cli.output import (
    console,
    format_duration,
    format_status,
    format_timestamp,
    print_info,
    print_kv,
    print_section,
    render_workspace_header,
)
from lza_workbench.workflows.status_root import (
    PipelineSummary,
    RootStatusResult,
    get_root_status_workflow,
)


def _render_pipeline_summary(
    pipe: PipelineSummary,
    *,
    label_prefix: str,
) -> None:
    print_kv(f"{label_prefix} Pipeline", pipe.name, bold_value=True)
    if not pipe.is_live:
        if pipe.status:
            print_kv("Latest Execution", f"{format_status(pipe.status)} (Recorded)")
        else:
            print_kv("Latest Execution", "None Recorded", style="dim")
        if pipe.execution_id:
            print_kv("Execution ID", f"{pipe.execution_id} (Recorded)", style="dim")
        if pipe.failed_stage:
            print_kv("Failed Stage", f"{pipe.failed_stage} (Recorded)", style="red")
        if pipe.failed_action:
            print_kv("Failed Action", f"{pipe.failed_action} (Recorded)", style="red")
        if pipe.failure_summary:
            print_kv("Failure", pipe.failure_summary, style="red")
        return

    if not pipe.exists:
        print_kv("Latest Execution", "[dim]Not Deployed[/dim]")
        return

    print_kv("Latest Execution", format_status(pipe.status or "Unknown"))
    if pipe.execution_id:
        print_kv("Execution ID", pipe.execution_id, style="dim")
    if pipe.start_time:
        print_kv("Started", format_timestamp(pipe.start_time))
    if pipe.duration_seconds is not None:
        dur_str = format_duration(pipe.duration_seconds)
        if dur_str:
            print_kv("Duration", dur_str)
    if pipe.current_stage or pipe.current_action:
        stage_act = " / ".join(filter(None, [pipe.current_stage, pipe.current_action]))
        print_kv("Current Stage/Action", stage_act, style="yellow")
    if pipe.failed_stage:
        print_kv("Failed Stage", pipe.failed_stage, style="red")
    if pipe.failed_action:
        print_kv("Failed Action", pipe.failed_action, style="red")
    if pipe.failure_summary:
        print_kv("Failure", pipe.failure_summary, style="red")


def render_root_status(result: RootStatusResult) -> None:
    """Render a root status result without querying AWS or the filesystem."""
    render_workspace_header(
        "LZA Workspace Summary",
        customer_name=result.customer_name,
        workspace_dir=result.workspace_dir,
        lza_version=result.lza_version,
        profile=result.profile,
        region=result.region,
        aws_identity=result.aws_identity,
        aws_error=result.aws_error,
    )

    # 1. Installer Summary
    console.print()
    print_section(1, "Installer")
    inst_stack = result.installer
    print_kv("Stack Name", inst_stack.name, bold_value=True)
    if inst_stack.is_live:
        if inst_stack.exists:
            print_kv("Stack Status", format_status(inst_stack.status))
            if inst_stack.deployed_version:
                print_kv("Deployed Version", inst_stack.deployed_version, bold_value=True)
        else:
            print_info("Stack Status: Not Deployed / Not Found", dim=True)
    else:
        if inst_stack.status:
            print_kv("Stack Status", f"{format_status(inst_stack.status)} (Recorded)")
        else:
            print_kv("Stack Status", "Not Recorded", style="dim")
        if inst_stack.deployed_version:
            print_kv("Deployed Version", f"{inst_stack.deployed_version} (Recorded)")
        else:
            print_kv("Deployed Version", "Not Recorded", style="dim")

    console.print()
    _render_pipeline_summary(result.installer_pipeline, label_prefix="Installer")

    # 2. Configuration Summary
    console.print()
    print_section(2, "Configuration")
    crepo = result.configuration_repo
    target_str = f"{crepo.repository_type} / {crepo.target or 'Not configured'}"
    print_kv("Repository", target_str, bold_value=True)

    if crepo.local_git_branch:
        tree_state = (
            "[green]Clean[/green]"
            if crepo.local_git_clean
            else f"[yellow]Dirty ({crepo.local_git_uncommitted} uncommitted)[/yellow]"
        )
        print_kv("Local Git", f"{crepo.local_git_branch} ({tree_state})")
    else:
        print_kv("Local Git", "Not a git repository", style="dim")

    if crepo.remote_sync_summary:
        print_kv("Remote Sync", format_status(crepo.remote_sync_summary))

    console.print()
    _render_pipeline_summary(result.configuration_pipeline, label_prefix="Configuration")

    # 3. Overall Status Summary
    console.print()
    print_section(3, "Overall Status")
    health = result.health
    print_kv("Installer", format_status(health.installer))
    print_kv("Configuration", format_status(health.configuration))
    print_kv("Workspace", format_status(health.workspace), bold_value=True)

    console.print()
    console.print("[bold cyan]Subcommands available for filtered status details:[/bold cyan]")
    console.print(
        "  [bold green]lza status installer[/bold green]  "
        "[dim](Detailed stack & pipeline status, drift & sync)[/dim]"
    )
    console.print(
        "  [bold green]lza status config[/bold green]     "
        "[dim](Detailed configuration repo status & sync)[/dim]"
    )


def status_root_command(
    target_dir: Path | None = None,
) -> None:
    """Display overall summary status for the customer LZA workspace."""
    result = get_root_status_workflow(target_dir=target_dir)
    render_root_status(result)


__all__ = [
    "render_root_status",
    "status_root_command",
]

