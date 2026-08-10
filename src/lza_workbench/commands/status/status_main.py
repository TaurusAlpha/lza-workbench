"""Root LZA Workbench status summary command."""

from __future__ import annotations

from pathlib import Path

from rich.panel import Panel

from lza_workbench.aws.client_factory import AwsClientFactory
from lza_workbench.aws.cloudformation import get_cloudformation_stack_status
from lza_workbench.core.workspace import (
    WorkspaceReadinessLevel,
    load_workspace_context,
)
from lza_workbench.utils.output import (
    console,
    print_info,
    print_kv,
    print_notice,
    print_section,
)


def run_root_status(
    *,
    aws_profile: str | None = None,
    aws_region: str | None = None,
    target_dir: Path | None = None,
) -> None:
    """Display overall summary status for the customer LZA workspace."""
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED)
    workspace_dir, config = ctx.workspace_dir, ctx.config

    profile = (aws_profile or "").strip() or (config.aws.profile or "").strip()
    region = (aws_region or "").strip() or (config.aws.region or "").strip() or "us-east-1"

    factory = None
    aws_identity = None
    aws_error = None
    if profile:
        try:
            factory = AwsClientFactory(profile, region)
            aws_identity = factory.validate_identity()
        except Exception as exc:  # noqa: BLE001
            aws_error = str(exc)

    console.print(
        Panel(
            f"[bold cyan]LZA Workspace Summary - {config.customer.name}[/bold cyan]",
            expand=False,
        )
    )

    print_kv("Customer Name", config.customer.name, bold_value=True)
    print_kv("Workspace Directory", workspace_dir, bold_value=True)
    print_kv("Configured LZA Version", config.lza.version, bold_value=True)
    print_kv("AWS Profile", profile or "Not specified", bold_value=True)
    print_kv("AWS Region", region, bold_value=True)

    if aws_identity:
        print_kv("AWS Account ID", aws_identity["account"], style="green")
        print_kv("Caller Identity", aws_identity["arn"], style="dim")
    elif aws_error:
        print_notice(f"AWS Access Notice: {aws_error}")

    # 1. Installer Summary
    console.print()
    print_section(1, "Installer Stack Status Overview")
    cfn_stack_name = config.installer.stack_name or "AWSAccelerator-InstallerStack"
    cfn_client = factory.get_client("cloudformation") if factory else None
    cfn_status = get_cloudformation_stack_status(client=cfn_client, stack_name=cfn_stack_name)

    print_kv("Installer Stack Name", cfn_stack_name)
    if cfn_status.exists:
        status_str = cfn_status.stack_status or "UNKNOWN"
        status_color = "green" if "COMPLETE" in status_str else "yellow"
        console.print(f"Stack Status: [{status_color}][bold]{status_str}[/bold][/{status_color}]")
    else:
        print_info("Stack Status: Not Deployed / Not Found", dim=True)

    # 2. Configuration Summary
    console.print()
    print_section(2, "Configuration Repository Overview")
    repo_config = config.configuration.repository
    print_kv("Repository Type", repo_config.type, bold_value=True)

    config_dir = workspace_dir / config.configuration.local_path
    exists_str = "[green]Present[/green]" if config_dir.exists() else "[red]Missing[/red]"
    print_kv("Local Config Directory", f"{config_dir} ({exists_str})")

    # 3. Pipelines Summary
    console.print()
    print_section(3, "Pipelines Overview")
    prefix = config.lza.accelerator_prefix or "AWSAccelerator"
    print_kv("Installer Pipeline", f"{prefix}-Installer")
    print_kv("Configuration Pipeline", f"{prefix}-Pipeline")

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
