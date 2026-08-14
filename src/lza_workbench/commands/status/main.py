"""Root LZA Workbench status summary command."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich.panel import Panel

from lza_workbench.aws.cloudformation import get_cloudformation_stack_status
from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.utils.output import (
    console,
    print_info,
    print_kv,
    print_notice,
    print_section,
)
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context


@dataclass(frozen=True)
class RootStatusResult:
    """All data needed to render the root workspace status report."""

    workspace_dir: Path
    customer_name: str
    lza_version: str
    profile: str
    region: str
    aws_identity: dict[str, str] | None
    aws_error: str | None
    stack_name: str
    stack_status: str | None
    stack_exists: bool
    repository_type: str
    config_dir: Path
    config_dir_exists: bool
    installer_pipeline_name: str
    config_pipeline_name: str


def run_root_status(
    *,
    target_dir: Path | None = None,
) -> None:
    """Display overall summary status for the customer LZA workspace."""
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED)
    workspace_dir, config = ctx.workspace_dir, ctx.config

    profile = config.aws.profile or ""
    region = config.aws.region or "us-east-1"

    aws_context = resolve_aws_execution_context(config.aws)
    factory = aws_context.factory
    region = aws_context.region
    aws_identity = aws_context.identity
    aws_error = aws_context.error
    cfn_stack_name = config.installer.stack_name or "AWSAccelerator-InstallerStack"
    cfn_client = factory.get_client("cloudformation") if aws_identity else None
    cfn_status = get_cloudformation_stack_status(client=cfn_client, stack_name=cfn_stack_name)

    result = RootStatusResult(
        workspace_dir=workspace_dir,
        customer_name=config.customer.name,
        lza_version=config.lza.version,
        profile=profile,
        region=region,
        aws_identity=aws_identity,
        aws_error=aws_error,
        stack_name=cfn_stack_name,
        stack_status=cfn_status.stack_status,
        stack_exists=cfn_status.exists,
        repository_type=config.configuration.repository.type,
        config_dir=workspace_dir / config.configuration.local_path,
        config_dir_exists=(workspace_dir / config.configuration.local_path).exists(),
        installer_pipeline_name=f"{config.lza.accelerator_prefix or 'AWSAccelerator'}-Installer",
        config_pipeline_name=f"{config.lza.accelerator_prefix or 'AWSAccelerator'}-Pipeline",
    )
    render_root_status(result)


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
