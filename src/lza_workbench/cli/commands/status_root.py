"""CLI command and presentation for root workspace status."""

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
from lza_workbench.workflows.status_root import (
    RootStatusResult,
    get_root_status_workflow,
)


def render_root_status(result: RootStatusResult) -> None:
    """Render a root status result without querying AWS or the filesystem."""
    console.print(
        Panel(
            f"[bold cyan]LZA Workspace Summary - {result.customer_name}[/bold cyan]",
            expand=False,
        )
    )

    print_kv("Customer Name", result.customer_name, bold_value=True)
    print_kv("Workspace Directory", result.workspace_dir, bold_value=True)
    print_kv("Configured LZA Version", result.lza_version, bold_value=True)
    print_kv("AWS Profile", result.profile or "Not specified", bold_value=True)
    print_kv("AWS Region", result.region, bold_value=True)

    if result.aws_identity:
        print_kv("AWS Account ID", result.aws_identity["account"], style="green")
        print_kv("Caller Identity", result.aws_identity["arn"], style="dim")
    elif result.aws_error:
        print_notice(f"AWS Access Notice: {result.aws_error}")

    # 1. Installer Summary
    console.print()
    print_section(1, "Installer Stack Status Overview")
    print_kv("Installer Stack Name", result.stack_name)
    if result.stack_exists:
        status_str = result.stack_status or "UNKNOWN"
        status_color = "green" if "COMPLETE" in status_str else "yellow"
        console.print(f"Stack Status: [{status_color}][bold]{status_str}[/bold][/{status_color}]")
    else:
        print_info("Stack Status: Not Deployed / Not Found", dim=True)

    # 2. Configuration Summary
    console.print()
    print_section(2, "Configuration Repository Overview")
    print_kv("Repository Type", result.repository_type, bold_value=True)

    exists_str = "[green]Present[/green]" if result.config_dir_exists else "[red]Missing[/red]"
    print_kv("Local Config Directory", f"{result.config_dir} ({exists_str})")

    if result.config_status:
        cs = result.config_status
        if cs.git_working_tree:
            gwt = cs.git_working_tree
            tree_str = (
                "[green]Clean[/green]"
                if not gwt.has_uncommitted
                else f"[yellow]Dirty ({gwt.uncommitted_count} uncommitted)[/yellow]"
            )
            print_kv("Git Working Tree", f"Branch: {gwt.branch} ({tree_str})")
            if cs.git_sync_status and cs.git_sync_status.status != "Not Git":
                print_kv("Remote Git Sync", cs.git_sync_status.summary)
        if cs.repository_type == "s3":
            s3_status = (
                "Available"
                if cs.s3_bucket_exists
                else "Not Found / Missing"
                if cs.s3_bucket_exists is False
                else "Inaccessible"
                if cs.s3_bucket_accessible is False
                else "Configured"
            )
            s3_col = (
                "green"
                if cs.s3_bucket_exists
                else "red"
                if cs.s3_bucket_exists is False or cs.s3_bucket_accessible is False
                else "dim"
            )
            bucket_str = cs.repository_bucket or "Not set"
            print_kv("S3 Target", f"{bucket_str} ([{s3_col}]{s3_status}[/{s3_col}])")
        elif cs.repository_type == "codecommit":
            cc_status = (
                "Available"
                if cs.codecommit_exists
                else "Not Found"
                if cs.codecommit_exists is False
                else "Inaccessible"
                if cs.codecommit_accessible is False
                else "Configured"
            )
            cc_col = (
                "green"
                if cs.codecommit_exists
                else "red"
                if cs.codecommit_exists is False or cs.codecommit_accessible is False
                else "dim"
            )
            repo_str = cs.repository_name or "Not set"
            print_kv("CodeCommit Target", f"{repo_str} ([{cc_col}]{cc_status}[/{cc_col}])")
        elif cs.repository_type == "codeconnection":
            c_status = cs.codeconnection_status or "Configured"
            c_col = (
                "green"
                if c_status == "AVAILABLE"
                else "yellow"
                if c_status == "PENDING"
                else "dim"
            )
            print_kv(
                "CodeConnection Target",
                f"{cs.owner}/{cs.repository_name} ([{c_col}]{c_status}[/{c_col}])",
            )



    # 3. Pipelines Summary
    console.print()
    print_section(3, "Pipelines Overview")
    print_kv("Installer Pipeline", result.installer_pipeline_name)
    print_kv("Configuration Pipeline", result.config_pipeline_name)

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
    console.print(
        "  [bold green]lza status pipeline[/bold green]   "
        "[dim](Detailed CodePipeline execution status)[/dim]"
    )


def status_root_command(
    target_dir: Path | None = None,
) -> None:
    """Display overall summary status for the customer LZA workspace."""
    result = get_root_status_workflow(target_dir=target_dir)
    render_root_status(result)
