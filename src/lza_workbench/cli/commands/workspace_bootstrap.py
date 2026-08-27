"""CLI command and presentation for bootstrapping LZA Workbench AWS prerequisite resources."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel

from lza_workbench.cli import params
from lza_workbench.cli.output import (
    console,
    print_dry_run_header,
    print_info,
    print_kv,
    print_notice,
    print_section,
)
from lza_workbench.workflows.workspace_bootstrap import (
    BootstrapPlanResult,
    WorkspaceBootstrapResult,
    apply_bootstrap_preparation,
    prepare_bootstrap_workflow,
)


def _render_bootstrap_plan(plan: BootstrapPlanResult) -> None:
    """Render planned bootstrap actions for user inspection."""
    title = f"[bold cyan]LZA Bootstrap Plan - {plan.config.customer.name}[/bold cyan]"
    if plan.dry_run:
        title += " [yellow](Dry Run)[/yellow]"

    console.print(Panel(title, expand=False))
    print_section(1, "Bootstrap Target")
    print_kv("Workspace", plan.workspace_dir, bold_value=True)
    print_kv("Target AWS Profile", plan.aws_profile or "default")
    print_kv("Target Region", plan.aws_region)
    print_kv("Target Account", plan.account_id)
    print_kv("Assets S3 Bucket", plan.bucket_name, bold_value=True)
    print_kv(
        "Current Bucket Status",
        "EXISTS" if plan.bucket_exists else "DOES NOT EXIST",
        bold_value=True,
    )
    if plan.bucket_exists:
        print_kv("Versioning Enabled", str(plan.versioning_enabled))
        print_kv("KMS Encryption Enabled", str(plan.encryption_enabled))

    if plan.codecommit_repo_name:
        console.print()
        print_kv("Config CodeCommit Repo", plan.codecommit_repo_name, bold_value=True)
        print_kv("Target Branch", plan.codecommit_branch_name or "main")
        print_kv(
            "Repo Status",
            "EXISTS" if plan.codecommit_repo_exists else "DOES NOT EXIST",
            bold_value=True,
        )

    op_color = (
        "green"
        if plan.planned_operation == "CREATE"
        else ("yellow" if plan.planned_operation == "UPDATE" else "blue")
    )
    print_kv(
        "Planned Action",
        f"[{op_color}][bold]{plan.planned_operation}[/bold][/{op_color}]",
    )

    console.print()
    print_section(2, "Planned AWS Actions")
    for action in plan.actions:
        console.print(f"  • {action}")


def _confirm_bootstrap(
    *,
    plan: BootstrapPlanResult,
    dry_run: bool,
    force: bool,
) -> bool:
    """Prompt user for confirmation before mutating AWS resources."""
    if dry_run or force or plan.planned_operation == "NO_CHANGE":
        return True

    prompt = (
        f"Proceed with {plan.planned_operation.lower()} for AWS bootstrap resources?"
    )
    if not typer.confirm(prompt, default=True):
        console.print("[dim]Bootstrap aborted by user.[/dim]")
        return False
    return True


def workspace_bootstrap_command(
    dry_run: params.DryRun = False,
    force: params.Force = False,
    target_dir: Path | None = None,
    interactive: bool = True,
) -> WorkspaceBootstrapResult | None:
    """Create or validate AWS prerequisite resources required by LZA Workbench."""
    del interactive
    preparation = prepare_bootstrap_workflow(target_dir=target_dir, dry_run=dry_run)
    plan = preparation.plan
    _render_bootstrap_plan(plan)

    if dry_run:
        console.print()
        print_dry_run_header("lza bootstrap")
        console.print(
            f"[bold yellow]Dry run:[/bold yellow] would execute "
            f"[bold green]{plan.planned_operation}[/bold green] for assets bucket "
            f"'{plan.bucket_name}'."
        )
        return None

    if not _confirm_bootstrap(plan=plan, dry_run=dry_run, force=force):
        return None

    console.print()
    print_info("Executing LZA Workbench bootstrap...", dim=True)
    result = apply_bootstrap_preparation(preparation=preparation)

    console.print()
    print_notice(
        f"Workbench assets bucket '{result.bucket_name}' is ready ({result.planned_operation})."
    )
    print_info(
        "Updated assets bucket in lza-workspace.yaml and operational state in .lza/state.json",
        dim=True,
    )
    for action in result.actions_taken:
        console.print(f"  ✓ {action}")

    return result


__all__ = [
    "BootstrapPlanResult",
    "WorkspaceBootstrapResult",
    "_confirm_bootstrap",
    "_render_bootstrap_plan",
    "apply_bootstrap_preparation",
    "prepare_bootstrap_workflow",
    "workspace_bootstrap_command",
]
