"""CLI command and presentation for deploying the LZA installer stack."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from rich.table import Table

from lza_workbench.cli import params
from lza_workbench.cli.output import (
    console,
    print_dry_run_header,
    print_info,
    print_kv,
    print_notice,
    print_section,
)
from lza_workbench.workflows.installer_deploy import (
    CfnDeploymentPlanResult,
    CfnStackStatusResult,
    InstallerConfigValidationError,
    InstallerConfigValidationResult,
    InstallerDeploymentPreparation,
    InstallerDeployResult,
    apply_installer_deployment,
    prepare_installer_deployment,
)


def _render_deployment_plan(
    *,
    stack_name: str,
    profile: str,
    region: str,
    account_id: str,
    plan: CfnDeploymentPlanResult,
    operation: str,
) -> None:
    print_section(1, "Deployment Target")
    print_kv("Target AWS Profile", profile or "default")
    print_kv("Target Region", region)
    print_kv("Target Account", account_id or "RESOLVED")
    print_kv("CloudFormation Stack", stack_name)
    print_kv("Current Stack Status", plan.stack_status or "DOES NOT EXIST")
    print_kv("Planned Action", operation, bold_value=True)

    if plan.parameter_diffs:
        console.print()
        print_section(2, "Parameter Changes")
        table = Table(title="Parameter Changes", show_header=True)
        table.add_column("Parameter Key", style="cyan")
        table.add_column("Current Deployed", style="red")
        table.add_column("New Value", style="green")
        for key, (current_val, new_val) in sorted(plan.parameter_diffs.items()):
            table.add_row(key, current_val, new_val)
        console.print(table)


def _confirm_deployment(
    *, operation: str, stack_name: str, dry_run: bool, force: bool
) -> bool:
    if dry_run or force:
        return True
    prompt = f"Proceed with CloudFormation stack {operation.lower()} for '{stack_name}'?"
    if not typer.confirm(prompt, default=True):
        console.print("[dim]Deployment aborted by user.[/dim]")
        return False
    return True


def _render_dry_run(*, operation: str, stack_name: str) -> None:
    print_dry_run_header("lza installer deploy")
    console.print(
        f"[bold yellow]Dry run:[/bold yellow] would execute "
        f"[bold green]{operation}[/bold green] on stack '{stack_name}'."
    )


def _render_stack_event(event: dict[str, Any]) -> None:
    resource_type = event.get("ResourceType", "")
    logical_id = event.get("LogicalResourceId", "")
    status = event.get("ResourceStatus", "")
    reason = event.get("ResourceStatusReason", "")

    color = "green" if "COMPLETE" in status else "red" if "FAILED" in status else "yellow"
    msg = f"  [{color}]{status:<25}[/{color}] {resource_type:<35} {logical_id}"
    if reason and "FAILED" in status:
        msg += f" ({reason})"
    console.print(msg)


def _render_missing_configuration(validation: InstallerConfigValidationResult) -> None:
    console.print(
        "[bold red]Configuration error: missing required installer settings in "
        "lza-workspace.yaml:[/bold red]"
    )
    for spec in validation.missing_fields:
        console.print(f"  - [bold]{spec.label}[/bold] ({spec.section}.{spec.attribute})")


def installer_deploy_command(
    dry_run: params.DryRun = False,
    force: params.Force = False,
    target_dir: Path | None = None,
) -> None:
    """Deploy the LZA installer CloudFormation stack for the current workspace."""
    try:
        preparation = prepare_installer_deployment(target_dir=target_dir, dry_run=dry_run)
    except InstallerConfigValidationError as exc:
        _render_missing_configuration(exc.validation)
        raise

    _render_deployment_plan(
        stack_name=preparation.stack_name,
        profile=preparation.profile,
        region=preparation.aws_context.region,
        account_id=preparation.account_id,
        plan=preparation.cfn_plan,
        operation=preparation.operation,
    )

    operation = preparation.operation
    force_no_change = False
    if operation == "NO_CHANGE" and not force:
        if not typer.confirm("Force re-deployment of stack?", default=False):
            console.print("[dim]Deployment skipped as stack has no parameter changes.[/dim]")
            return
        force_no_change = True
        operation = "UPDATE"

    if not _confirm_deployment(
        operation=operation, stack_name=preparation.stack_name, dry_run=dry_run, force=force
    ):
        return

    if dry_run:
        _render_dry_run(operation=operation, stack_name=preparation.stack_name)
        return

    print_info(f"Initiating CloudFormation stack {operation}...", dim=True)
    result = apply_installer_deployment(
        preparation=preparation,
        dry_run=False,
        force=force,
        force_no_change=force_no_change,
        on_event=_render_stack_event,
    )

    if result.final_status:
        if result.skipped:
            print_notice(
                f"CloudFormation stack '{preparation.stack_name}' required no update "
                f"({result.final_status.stack_status})."
            )
        else:
            print_notice(
                f"CloudFormation stack '{preparation.stack_name}' deployed successfully "
                f"({result.final_status.stack_status})."
            )
        print_info("Updated operational state in .lza/state.json", dim=True)
        if result.final_status.outputs:
            table = Table(title="Stack Outputs", show_header=True)
            table.add_column("Key", style="bold cyan")
            table.add_column("Value", style="bold green")
            for k, v in sorted(result.final_status.outputs.items()):
                table.add_row(k, v)
            console.print(table)


__all__ = [
    "CfnDeploymentPlanResult",
    "CfnStackStatusResult",
    "InstallerConfigValidationError",
    "InstallerConfigValidationResult",
    "InstallerDeploymentPreparation",
    "InstallerDeployResult",
    "apply_installer_deployment",
    "_confirm_deployment",
    "_render_deployment_plan",
    "_render_dry_run",
    "_render_missing_configuration",
    "_render_stack_event",
    "installer_deploy_command",
    "prepare_installer_deployment",
]
