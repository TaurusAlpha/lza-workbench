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

    # 3. Pipelines Summary
    console.print()
    print_section(3, "Pipelines Overview")
    print_kv("Installer Pipeline", result.installer_pipeline_name)
    print_kv("Configuration Pipeline", result.config_pipeline_name)

    console.print()
    console.print("[bold cyan]Subcommands available for filtered status details:[/bold cyan]")
    console.print(
        "  [bold green]lza status installer[/bold green]  "
        "[dim](Detailed stack status, drift, outputs & sync)[/dim]"
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
