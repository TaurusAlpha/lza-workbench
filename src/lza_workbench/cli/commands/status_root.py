"""CLI command and presentation for root workspace status."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.cli.output import (
    console,
    format_status,
    print_info,
    print_kv,
    print_section,
    render_workspace_header,
)
from lza_workbench.workflows.status_root import (
    RootStatusResult,
    get_root_status_workflow,
)


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
    print_section(1, "Installer Stack")
    print_kv("Stack Name", result.stack_name, bold_value=True)
    if result.stack_exists:
        print_kv("Stack Status", format_status(result.stack_status))
    else:
        print_info("Stack Status: Not Deployed / Not Found", dim=True)

    # 2. Configuration Summary
    console.print()
    print_section(2, "Configuration Repository")
    print_kv("Repository Type", result.repository_type, bold_value=True)

    exists_str = "[green]Present[/green]" if result.config_dir_exists else "[red]Missing[/red]"
    print_kv("Local Config Path", f"{result.config_dir} ({exists_str})")

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
                print_kv("Remote Sync", cs.git_sync_status.summary)
        if cs.repository_type == "s3":
            s3_status = (
                "Available"
                if cs.s3_bucket_exists
                else "Not Found"
                if cs.s3_bucket_exists is False
                else "Inaccessible"
                if cs.s3_bucket_accessible is False
                else "Configured"
            )
            bucket_str = cs.repository_bucket or "Not configured"
            print_kv("S3 Target", f"{bucket_str} ({format_status(s3_status)})")
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
            repo_str = cs.repository_name or "Not set"
            print_kv("CodeCommit Target", f"{repo_str} ({format_status(cc_status)})")
        elif cs.repository_type == "codeconnection":
            c_status = cs.codeconnection_status or "Configured"
            print_kv(
                "CodeConnection Target",
                f"{cs.owner}/{cs.repository_name} ({format_status(c_status)})",
            )

    # 3. Pipelines Summary
    console.print()
    print_section(3, "Pipelines")
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


__all__ = [
    "render_root_status",
    "status_root_command",
]

