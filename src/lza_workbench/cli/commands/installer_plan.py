"""CLI command and presentation for LZA installer planning."""

from __future__ import annotations

from pathlib import Path

from rich.panel import Panel
from rich.table import Table

from lza_workbench.cli import params
from lza_workbench.cli.presentation import (
    console,
    print_info,
    print_kv,
    print_notice,
    print_section,
    print_warning,
)
from lza_workbench.workflows.installer_plan import (
    InstallerPlanResult,
    plan_installer_workflow,
)


def render_installer_plan_report(plan: InstallerPlanResult) -> None:
    """Render structured rich summary plan output for the user."""
    workspace_dir = plan.workspace_dir
    config = plan.config
    profile = plan.profile
    region = plan.region
    aws_identity = plan.aws_identity
    aws_error = plan.aws_error
    codecommit_plan = plan.codecommit_plan
    cfn_plan = plan.cloudformation_plan
    dry_run = plan.dry_run
    title = f"[bold cyan]LZA Installer Plan - {config.customer.name}[/bold cyan]"
    if dry_run:
        title += " [yellow](Dry Run)[/yellow]"

    console.print(Panel(title, expand=False))

    # General info
    print_kv("Workspace", workspace_dir, bold_value=True)
    print_kv("LZA Version", config.lza.version, bold_value=True)
    print_kv("AWS Profile", profile or "Not specified", bold_value=True)
    print_kv("AWS Region", region, bold_value=True)

    if aws_identity:
        print_kv("AWS Account ID", aws_identity["account"], style="green")
        print_kv("Caller Identity", aws_identity["arn"], style="dim")
    elif aws_error:
        print_notice(f"AWS Access Notice: {aws_error}")

    console.print()

    # CodeCommit Section
    print_section(1, "Source Code Repository Planning")
    print_kv("Source Type", config.installer.source_code.repository_type, bold_value=True)
    print_kv("Repository Name", codecommit_plan.repository_name)
    print_kv("Target Branch", codecommit_plan.branch_name)
    print_kv("Repository Status", codecommit_plan.status, bold_value=True)
    console.print("Planned Repository Actions:")
    for action in codecommit_plan.actions:
        console.print(f"  • {action}")

    console.print()

    # CloudFormation Section
    print_section(2, "CloudFormation Deployment Planning")
    print_kv("Stack Name", cfn_plan.stack_name, bold_value=True)
    op_color = (
        "green"
        if cfn_plan.operation == "CREATE"
        else ("yellow" if cfn_plan.operation == "UPDATE" else "blue")
    )
    console.print(
        f"Planned Stack Operation: [{op_color}][bold]{cfn_plan.operation}[/bold][/{op_color}]"
    )
    if cfn_plan.stack_status:
        print_kv("Current Stack Status", cfn_plan.stack_status)

    console.print()
    table = Table(title="Resolved CloudFormation Parameters", show_header=True)
    table.add_column("Parameter Key", style="cyan")
    table.add_column("Resolved Value", style="white")

    for k, v in sorted(cfn_plan.resolved_parameters.items()):
        table.add_row(k, str(v))

    console.print(table)

    if cfn_plan.parameter_diffs:
        diff_table = Table(title="Parameter Changes (Update Plan)", show_header=True)
        diff_table.add_column("Parameter Key", style="cyan")
        diff_table.add_column("Current Deployed Value", style="red")
        diff_table.add_column("Planned New Value", style="green")

        for k, (old_v, new_v) in sorted(cfn_plan.parameter_diffs.items()):
            diff_table.add_row(k, str(old_v), str(new_v))

        console.print(diff_table)

    console.print()
    print_warning("Plan Complete. Guarantee: No AWS resources were modified or deployed.")


def installer_plan_command(
    dry_run: params.DryRun = False,
    no_save: bool = False,
    target_dir: Path | None = None,
) -> None:
    """Resolve installer config from workspace and show planned deployment actions."""
    if not no_save and not dry_run:
        print_info("Installer configuration verified in lza-workspace.yaml", dim=True)

    plan_result = plan_installer_workflow(
        target_dir=target_dir,
        dry_run=dry_run,
        no_save=no_save,
    )
    render_installer_plan_report(plan_result)
