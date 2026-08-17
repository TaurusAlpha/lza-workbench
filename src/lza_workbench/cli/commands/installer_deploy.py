"""CLI command and presentation for deploying the LZA installer stack."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from rich.panel import Panel
from rich.table import Table

from lza_workbench.aws.cloudformation import (
    CfnDeploymentPlanResult,
    inspect_cloudformation_stack,
)
from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.cli import params
from lza_workbench.cli.presentation import (
    console,
    print_info,
    print_kv,
    print_notice,
    print_section,
)
from lza_workbench.errors import LzaError
from lza_workbench.installer.deployment import (
    prepare_installer_template,
    validate_cloudformation_plan,
    validate_deployment_preflight,
)
from lza_workbench.workflows.installer_deploy import deploy_installer_workflow
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context


def _render_deployment_plan(
    *,
    stack_name: str,
    profile: str,
    region: str,
    account_id: str,
    plan: CfnDeploymentPlanResult,
) -> None:
    """Render the read-only CloudFormation deployment plan."""
    print_section(1, f"LZA Installer Stack Deployment ({plan.operation})")
    print_kv("Stack Name", stack_name)
    print_kv("AWS Account", account_id)
    print_kv("AWS Region", region)
    print_kv("AWS Profile", profile)
    print_kv("Operation", plan.operation)
    if plan.stack_status:
        print_kv("Current Stack Status", plan.stack_status)

    title = (
        "Parameter Changes to be Applied"
        if plan.parameter_diffs
        else "CloudFormation Parameters to be Deployed"
    )
    table = Table(title=title, show_header=True)
    table.add_column("Parameter Key", style="cyan")
    table.add_column("Current Deployed Value" if plan.parameter_diffs else "Value", style="white")
    if plan.parameter_diffs:
        table.add_column("Planned New Value", style="green")
        for key, (old_value, new_value) in sorted(plan.parameter_diffs.items()):
            table.add_row(key, str(old_value), str(new_value))
    else:
        for key, value in sorted(plan.resolved_parameters.items()):
            table.add_row(key, str(value))
    console.print(table)
    console.print()


def _confirm_deployment(*, operation: str, stack_name: str, dry_run: bool, force: bool) -> bool:
    """Prompt for AWS mutation unless it has been explicitly skipped or forced."""
    if force or dry_run:
        return True
    prompt = f"Proceed with CloudFormation stack deployment ({operation}) for '{stack_name}'?"
    if typer.confirm(prompt, default=True):
        return True
    console.print("[yellow]Deployment cancelled by user.[/yellow]")
    return False


def _render_dry_run(*, operation: str, stack_name: str) -> None:
    """Render the no-mutation dry-run result."""
    console.print(
        Panel(
            f"[bold green]Dry-run complete.[/bold green]\nWould execute CloudFormation "
            f"[bold]{operation}[/bold] for stack [bold]{stack_name}[/bold].\n"
            "No AWS resources were modified.",
            title="Dry Run Summary",
        )
    )


def _render_stack_event(event: dict[str, Any]) -> None:
    """Render a single CloudFormation event."""
    reason = event.get("ResourceStatusReason", "")
    reason_text = f" ({reason})" if reason else ""
    console.print(
        f"  [dim]{str(event.get('Timestamp', ''))[:19]}[/dim] "
        f"[bold]{event.get('LogicalResourceId', '')}[/bold] "
        f"({event.get('ResourceType', '')}) -> "
        f"[cyan]{event.get('ResourceStatus', '')}[/cyan]{reason_text}"
    )


def _render_missing_configuration(config: Any) -> None:
    """Render missing preflight fields while validation remains presentation-independent."""
    from lza_workbench.installer.config import validate_installer_configuration

    validation = validate_installer_configuration(config)
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
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.CONFIGURED)
    workspace_dir, config = ctx.workspace_dir, ctx.config
    profile = config.aws.profile or ""

    try:
        validate_deployment_preflight(config)
    except LzaError:
        _render_missing_configuration(config)
        raise

    try:
        aws_context = resolve_aws_execution_context(
            config.aws, require_identity=True, require_expected_account=True
        )
    except Exception as exc:
        raise LzaError(f"AWS authentication check failed for profile '{profile}': {exc}") from exc
    assert aws_context.identity is not None

    _, resolved_parameters = prepare_installer_template(
        workspace_dir=workspace_dir, config=config, dry_run=dry_run
    )

    stack_name = config.installer.stack_name or "AWSAccelerator-InstallerStack"
    cfn_plan = inspect_cloudformation_stack(
        client=aws_context.factory.get_client("cloudformation"),
        stack_name=stack_name,
        resolved_parameters=resolved_parameters,
    )
    operation = validate_cloudformation_plan(cfn_plan)

    _render_deployment_plan(
        stack_name=stack_name,
        profile=profile,
        region=aws_context.region,
        account_id=aws_context.identity["account"],
        plan=cfn_plan,
    )

    force_no_change = False
    if operation == "NO_CHANGE" and not force:
        if not typer.confirm("Force re-deployment of stack?", default=False):
            console.print("[dim]Deployment skipped as stack has no parameter changes.[/dim]")
            return
        force_no_change = True
        operation = "UPDATE"

    if not _confirm_deployment(
        operation=operation, stack_name=stack_name, dry_run=dry_run, force=force
    ):
        return

    if dry_run:
        _render_dry_run(operation=operation, stack_name=stack_name)
        return

    print_info(f"Initiating CloudFormation stack {operation}...", dim=True)
    result = deploy_installer_workflow(
        target_dir=target_dir,
        dry_run=dry_run,
        force=force,
        force_no_change=force_no_change,
        on_event=_render_stack_event,
    )

    if result.final_status:
        print_notice(
            f"CloudFormation stack '{stack_name}' deployed successfully "
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
