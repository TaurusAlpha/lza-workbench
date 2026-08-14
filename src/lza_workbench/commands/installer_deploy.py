"""Deploy the LZA installer CloudFormation stack for the current workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from rich.panel import Panel
from rich.table import Table

from lza_workbench.aws.cloudformation import (
    CfnDeploymentPlanResult,
    CfnStackStatusResult,
    deploy_cloudformation_stack,
    inspect_cloudformation_stack,
    stream_cloudformation_stack_events,
)
from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.core.errors import LzaError
from lza_workbench.installer.deployment import (
    inspect_installer_source,
    prepare_installer_template,
    update_successful_deployment_state,
    validate_cloudformation_plan,
    validate_deployment_preflight,
)
from lza_workbench.utils.output import (
    console,
    print_info,
    print_kv,
    print_notice,
    print_section,
)
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context


def run_installer_deploy(
    *, dry_run: bool = False, force: bool = False, target_dir: Path | None = None
) -> None:
    """Deploy the LZA installer stack through explicit, independently testable stages."""
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

    template_path, resolved_parameters = prepare_installer_template(
        workspace_dir=workspace_dir, config=config, dry_run=dry_run
    )
    inspect_installer_source(factory=aws_context.factory, config=config, region=aws_context.region)

    stack_name = config.installer.stack_name or "AWSAccelerator-InstallerStack"
    cfn_plan = inspect_cloudformation_stack(
        factory=aws_context.factory,
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

    if operation == "NO_CHANGE" and not force:
        if not typer.confirm("Force re-deployment of stack?", default=False):
            console.print("[dim]Deployment skipped as stack has no parameter changes.[/dim]")
            return
        operation = "UPDATE"

    if not _confirm_deployment(
        operation=operation, stack_name=stack_name, dry_run=dry_run, force=force
    ):
        return
    if dry_run:
        _render_dry_run(operation=operation, stack_name=stack_name)
        return

    stack_id = _deploy_stack(
        factory=aws_context.factory,
        stack_name=stack_name,
        template_path=template_path,
        parameters=resolved_parameters,
        operation=operation,
    )
    final_status = stream_cloudformation_stack_events(
        factory=aws_context.factory, stack_name=stack_name, on_event=_render_stack_event
    )
    _handle_deployment_result(
        final_status=final_status,
        stack_id=stack_id,
        stack_name=stack_name,
        workspace_dir=workspace_dir,
        aws_identity=aws_context.identity,
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


def _deploy_stack(
    *,
    factory: Any,
    stack_name: str,
    template_path: Path,
    parameters: dict[str, str],
    operation: str,
) -> str:
    """Start a safe CloudFormation operation after confirmation."""
    print_info(f"Initiating CloudFormation stack {operation}...", dim=True)
    stack_id = deploy_cloudformation_stack(
        factory=factory,
        stack_name=stack_name,
        template_body=template_path.read_text(encoding="utf-8"),
        parameters=parameters,
        operation=operation,
    )
    print_info(f"Stack operation initiated (Stack ID: {stack_id}). Streaming events...", dim=True)
    return stack_id


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


def _handle_deployment_result(
    *,
    final_status: CfnStackStatusResult,
    stack_id: str,
    stack_name: str,
    workspace_dir: Path,
    aws_identity: dict[str, str],
) -> None:
    """Persist successful state and render the final deployment outcome."""
    if final_status.stack_status not in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}:
        console.print(
            f"[bold red]Deployment failed with stack status "
            f"({final_status.stack_status}).[/bold red]"
        )
        if final_status.error:
            console.print(f"[red]Error detail: {final_status.error}[/red]")
        raise LzaError(f"Deployment failed with stack status ({final_status.stack_status}).")

    print_notice(
        f"CloudFormation stack '{stack_name}' deployed successfully "
        f"({final_status.stack_status})."
    )
    update_successful_deployment_state(
        workspace_dir=workspace_dir,
        aws_identity=aws_identity,
        stack_id=final_status.stack_id or stack_id,
        stack_status=final_status.stack_status,
    )
    print_info("Updated operational state in .lza/state.json", dim=True)
    if final_status.outputs:
        table = Table(title="Stack Outputs", show_header=True)
        table.add_column("Key", style="bold cyan")
        table.add_column("Value", style="green")
        for key, value in final_status.outputs.items():
            table.add_row(key, value)
        console.print(table)
