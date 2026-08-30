"""CLI command and presentation for installer stack status."""

from __future__ import annotations

from pathlib import Path

from rich.table import Table

from lza_workbench.cli.output import (
    console,
    format_status,
    format_timestamp,
    print_info,
    print_kv,
    print_notice,
    print_section,
    render_workspace_header,
)
from lza_workbench.workflows.status_installer import (
    InstallerStatusResult,
    get_installer_status_workflow,
    normalize_lza_version,
)


def _render_resources(result: InstallerStatusResult) -> None:
    console.print()
    print_section(1, "Installer Stack")
    status = result.cfn_status.stack_status or "UNKNOWN"
    stack_name = result.config.installer.stack_name or "AWSAccelerator-InstallerStack"

    print_kv("Target Region", result.region, bold_value=True)
    print_kv("Installer Stack Name", stack_name, bold_value=True)
    print_kv("Stack Status", format_status(status))
    print_kv("Installer Pipeline Name", result.installer_pipeline_name, bold_value=True)

    if result.pipeline_state:
        pipe_status = result.pipeline_state.status or "UNKNOWN"
        print_kv("Pipeline Status", format_status(pipe_status))
        if result.pipeline_state.latest_execution_id:
            print_kv(
                "Latest Execution ID",
                result.pipeline_state.latest_execution_id,
                style="dim",
            )
        if result.pipeline_state.stage_states:
            stage_parts = []
            for s in result.pipeline_state.stage_states:
                s_status = s.status or "Unknown"
                stage_parts.append(f"{s.stage_name} ({format_status(s_status)})")
            print_kv("Pipeline Stages", " -> ".join(stage_parts))
        if result.pipeline_state.error:
            print_notice(f"Pipeline Query Notice: {result.pipeline_state.error}")

    created = format_timestamp(result.cfn_status.creation_time)
    if created:
        print_kv("Stack Creation Time", created)
    updated = format_timestamp(result.cfn_status.last_updated_time)
    if updated:
        print_kv("Stack Last Updated", updated)
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


def _render_state_alignment(result: InstallerStatusResult) -> None:
    console.print()
    print_section(4, "State Alignment")
    if not result.state:
        print_info("No recorded workspace state found.", dim=True)
        return
    state = result.state
    rec_status = (
        format_status(state.installer_stack_status)
        if state.installer_stack_status
        else None
    )
    for label, value in (
        ("Recorded Stack ID", state.installer_stack_id),
        ("Recorded Stack Status", rec_status),
        ("Recorded Stack Updated", format_timestamp(state.installer_stack_updated_at)),
        ("Installer Downloaded", format_timestamp(state.installer_downloaded_at)),
        ("Template Version", state.installer_template_version),
    ):

        if value:
            print_kv(label, value)
    if result.state_alignment:
        print_kv(
            "State Alignment",
            "In Sync (Recorded state matches live AWS deployment)"
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
    if result.configuration_drift or state_out_of_sync:
        console.print(
            "  [bold green]lza installer import[/bold green]  "
            "[dim](Synchronizes lza-workspace.yaml and recorded state "
            "with live AWS settings)[/dim]"
        )
        console.print(
            "  [bold green]lza installer deploy[/bold green]  "
            "[dim](Reconcile deployed installer stack with local configuration values)[/dim]"
        )


def render_installer_status(result: InstallerStatusResult) -> None:
    """Render prepared installer data without AWS calls or workspace writes."""
    render_workspace_header(
        "LZA Installer Status",
        customer_name=result.config.customer.name,
        workspace_dir=result.workspace_dir,
        lza_version=result.config.lza.version,
        profile=result.profile,
        region=result.region,
        aws_identity=result.aws_identity,
        aws_error=result.aws_error,
    )
    _render_resources(result)
    _render_deployed_details(result)
    _render_drift(result)
    _render_state_alignment(result)
    _render_recommendations(result)


def status_installer_command(
    target_dir: Path | None = None,
) -> None:
    """Query AWS and render an installer status report."""
    result = get_installer_status_workflow(
        target_dir=target_dir,
    )
    render_installer_status(result)


__all__ = [
    "render_installer_status",
    "status_installer_command",
]

