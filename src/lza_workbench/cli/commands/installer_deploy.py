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
from lza_workbench.aws.cloudformation import (
    CfnDeploymentPlanResult,
    CfnStackStatusResult,
)
from lza_workbench.installer.deployment import (
    InstallerConfigValidationError,
    InstallerConfigValidationResult,
)
from lza_workbench.workflows.installer_deploy import (
    InstallerDeployResult,
    deploy_installer_workflow,
)


def _render_deployment_plan(
    *,
    stack_name: str,
    profile: str,
    region: str,
    account_id: str,
    plan: CfnDeploymentPlanResult,
) -> None:
    print_section(1, "Deployment Target")
    print_kv("Target AWS Profile", profile or "default")
    print_kv("Target Region", region)
    print_kv("Target Account", account_id or "RESOLVED")
    print_kv("CloudFormation Stack", stack_name)
    print_kv("Current Stack Status", plan.stack_status or "DOES NOT EXIST")
    print_kv("Planned Action", plan.operation, bold_value=True)

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
        plan_result = deploy_installer_workflow(
            target_dir=target_dir,
            dry_run=True,
            force=force,
        )
    except InstallerConfigValidationError as exc:
        _render_missing_configuration(exc.validation)
        raise

    _render_deployment_plan(
        stack_name=plan_result.stack_name,
        profile=plan_result.profile,
        region=plan_result.region,
        account_id=plan_result.account_id,
        plan=plan_result.cfn_plan,
    )

    operation = plan_result.operation
    force_no_change = False
    if operation == "NO_CHANGE" and not force:
        if not typer.confirm("Force re-deployment of stack?", default=False):
            console.print("[dim]Deployment skipped as stack has no parameter changes.[/dim]")
            return
        force_no_change = True
        operation = "UPDATE"

    if not _confirm_deployment(
        operation=operation, stack_name=plan_result.stack_name, dry_run=dry_run, force=force
    ):
        return

    if dry_run:
        _render_dry_run(operation=operation, stack_name=plan_result.stack_name)
        return

    print_info(f"Initiating CloudFormation stack {operation}...", dim=True)
    result = deploy_installer_workflow(
        target_dir=target_dir,
        dry_run=False,
        force=force,
        force_no_change=force_no_change,
        on_event=_render_stack_event,
    )

    if result.final_status:
        print_notice(
            f"CloudFormation stack '{plan_result.stack_name}' deployed successfully "
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
    "InstallerDeployResult",
    "_confirm_deployment",
    "_render_deployment_plan",
    "_render_dry_run",
    "_render_missing_configuration",
    "_render_stack_event",
    "deploy_installer_workflow",
    "installer_deploy_command",
]
