"""CLI command and presentation for installer stack status."""

from __future__ import annotations

from pathlib import Path

from rich.panel import Panel
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
from lza_workbench.workflows.status_installer import (
    InstallerStatusResult,
    get_installer_status_workflow,
    normalize_lza_version,
)


def _render_resources(result: InstallerStatusResult) -> None:
    console.print()
    print_section(1, "CloudFormation Stack & Pipeline Resources")
    status = result.cfn_status.stack_status or "UNKNOWN"
    account_id = result.aws_identity["account"] if result.aws_identity else "UNKNOWN_ACCOUNT"
    stack_name = result.config.installer.stack_name or "AWSAccelerator-InstallerStack"
    stack_arn = (
        result.cfn_status.stack_id
        or f"arn:aws:cloudformation:{result.region}:{account_id}:stack/{stack_name}/*"
    )
    color = (
        "green"
        if result.cfn_status.exists and "COMPLETE" in status
        else "yellow"
        if result.cfn_status.exists
        else "red"
        if status == "UNKNOWN"
        else "dim"
    )
    print_kv("Target Region", result.region, bold_value=True)
    print_kv("Installer CloudFormation Stack", stack_name, bold_value=True)
    print_kv("Installer Stack ARN", stack_arn, style="dim")
    console.print(f"Installer Stack Status: [{color}][bold]{status}[/bold][/{color}]")
    for label, name in (
        ("Installer", result.installer_pipeline_name),
        ("Config", result.config_pipeline_name),
    ):
        print_kv(f"{label} Pipeline Name", name, bold_value=True)
        print_kv(
            f"{label} Pipeline ARN",
            f"arn:aws:codepipeline:{result.region}:{account_id}:{name}",
            style="dim",
        )
    if result.cfn_status.creation_time:
        print_kv("Stack Creation Time", result.cfn_status.creation_time)
    if result.cfn_status.last_updated_time:
        print_kv("Stack Last Updated", result.cfn_status.last_updated_time)
    if result.cfn_status.error:
        print_notice(f"CloudFormation Query Notice: {result.cfn_status.error}")


def _render_deployed_details(result: InstallerStatusResult) -> None:
    console.print()
    print_section(2, "Deployed Installer Details")
    params_data = result.cfn_status.deployed_parameters
    if not result.cfn_status.exists or not params_data:
        print_kv(
            "Source Type", result.config.installer.source_code.repository_type, bold_value=True
        )
        print_kv("Repository", result.config.installer.source_code.repository_name or "N/A")
        print_info("Deployed details unavailable (stack not deployed or unreadable).", dim=True)
        return
    print_kv("Deployed LZA Version", result.deployed_version, bold_value=True)
    print_kv(
        "Source Type",
        params_data.get("RepositorySource", result.config.installer.source_code.repository_type),
        bold_value=True,
    )
    owner = params_data.get("RepositoryOwner", result.config.installer.source_code.owner or "N/A")
    repository_name = params_data.get(
        "RepositoryName", result.config.installer.source_code.repository_name or "N/A"
    )
    print_kv("Repository", f"{owner}/{repository_name}")
    print_kv("Branch", params_data.get("RepositoryBranchName", ""))
    matches = normalize_lza_version(result.config.lza.version) == normalize_lza_version(
        result.deployed_version
    )
    print_kv(
        "Version Match",
        "Match (Configured matches Deployed)"
        if matches
        else (
            f"Mismatch (Configured: {result.config.lza.version}, "
            f"Deployed: {result.deployed_version})"
        ),
        style="green" if matches else "yellow",
    )


def _render_drift(result: InstallerStatusResult) -> None:
    console.print()
    print_section(3, "Configuration Drift")
    if not result.cfn_status.exists or not result.cfn_status.deployed_parameters:
        print_info("Drift check skipped (stack is not deployed).", dim=True)
        return
    if not result.configuration_drift:
        print_info("No configuration drift detected.", style="green")
        return
    table = Table(title="Detected Parameter Drift", show_header=True)
    table.add_column("Parameter Key", style="cyan")
    table.add_column("Deployed Value", style="red")
    table.add_column("Configured Value", style="green")
    for key, (deployed, configured) in sorted(result.configuration_drift.items()):
        table.add_row(key, deployed, configured)
    console.print(table)


def _render_outputs(result: InstallerStatusResult) -> None:
    console.print()
    print_section(4, "Stack Outputs")
    if not result.cfn_status.outputs:
        print_info("No stack outputs available.", dim=True)
        return
    table = Table(title="CloudFormation Outputs", show_header=True)
    table.add_column("Output Key", style="cyan")
    table.add_column("Output Value", style="white")
    for key, value in sorted(result.cfn_status.outputs.items()):
        table.add_row(key, value)
    console.print(table)


def _render_state_alignment(result: InstallerStatusResult) -> None:
    console.print()
    print_section(5, "Local State Metadata (.lza/state.json)")
    if not result.state:
        print_info("No local state file found.", dim=True)
        return
    state = result.state
    for label, value in (
        ("State Stack ID", state.installer_stack_id),
        ("State Stack Status", state.installer_stack_status),
        ("State Stack Last Updated", state.installer_stack_updated_at),
        ("Installer Downloaded At", state.installer_downloaded_at),
        ("Installer Template Version", state.installer_template_version),
    ):
        print_kv(label, value or "Not recorded")
    if result.state_alignment:
        print_kv(
            "State Alignment",
            "In Sync (.lza/state.json matches live AWS state)"
            if result.state_alignment.in_sync
            else "Out of Sync",
            style="green" if result.state_alignment.in_sync else "yellow",
        )


def _render_recommendations(result: InstallerStatusResult) -> None:
    state_out_of_sync = result.state_alignment is not None and not result.state_alignment.in_sync
    if not result.cfn_status.exists or (not result.configuration_drift and not state_out_of_sync):
        return
    console.print()
    console.print("[bold cyan]Recommended Next Command:[/bold cyan]")
    if result.configuration_drift:
        console.print(
            "  [bold green]lza status installer --sync-config[/bold green]  "
            "[dim](Synchronizes lza-workspace.yaml and .lza/state.json "
            "with live AWS settings)[/dim]"
        )
        console.print(
            "  [bold green]lza installer deploy[/bold green]  "
            "[dim](Reconcile deployed installer stack with local configuration values)[/dim]"
        )
    else:
        console.print(
            "  [bold green]lza status installer --sync-state[/bold green]   "
            "[dim](Synchronizes .lza/state.json with live AWS installer deployment state)[/dim]"
        )


def render_installer_status(result: InstallerStatusResult) -> None:
    """Render prepared installer data without AWS calls or workspace writes."""
    console.print(
        Panel(
            f"[bold cyan]LZA Installer Status - {result.config.customer.name}[/bold cyan]",
            expand=False,
        )
    )
    print_kv("Workspace", result.workspace_dir, bold_value=True)
    print_kv("Configured LZA Version", result.config.lza.version, bold_value=True)
    print_kv("AWS Profile", result.profile or "Not specified", bold_value=True)
    print_kv("AWS Region", result.region, bold_value=True)
    if result.aws_identity:
        print_kv("AWS Account ID", result.aws_identity["account"], style="green")
        print_kv("Caller Identity", result.aws_identity["arn"], style="dim")
    elif result.aws_error:
        print_notice(f"AWS Access Notice: {result.aws_error}")
    _render_resources(result)
    _render_deployed_details(result)
    _render_drift(result)
    _render_outputs(result)
    _render_state_alignment(result)
    _render_recommendations(result)


def status_installer_command(
    sync_state: params.SyncState = False,
    sync_config: params.SyncConfig = False,
    target_dir: Path | None = None,
) -> None:
    """Query AWS, optionally synchronize, then render an installer status result."""
    result = get_installer_status_workflow(
        sync_state=sync_state,
        sync_config=sync_config,
        target_dir=target_dir,
    )
    if result.state_synced:
        console.print(
            "[bold green]Synchronized .lza/state.json with live AWS installer state.[/bold green]"
        )
    if result.config_synced:
        print_success("Synchronized lza-workspace.yaml with deployed AWS installer configuration.")

    render_installer_status(result)
