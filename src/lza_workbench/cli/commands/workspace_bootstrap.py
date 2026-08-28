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

    console.print()
    print_kv("Assets S3 Bucket", plan.bucket_name, bold_value=True)
    print_kv(
        "Current Bucket Status",
        "EXISTS" if plan.bucket_exists else "DOES NOT EXIST",
        bold_value=True,
    )
    if plan.bucket_exists:
        print_kv("Versioning Enabled", str(plan.versioning_enabled))
        print_kv("KMS Encryption Enabled", str(plan.encryption_enabled))
    print_kv("Bucket Planned Action", plan.bucket_planned_operation)

    if plan.codecommit_repo_name:
        console.print()
        print_kv("Config CodeCommit Repo", plan.codecommit_repo_name, bold_value=True)
        print_kv("Target Branch", plan.codecommit_branch_name or "main")
        print_kv(
            "Repo Status",
            "EXISTS" if plan.codecommit_repo_exists else "DOES NOT EXIST",
            bold_value=True,
        )
        print_kv("Repo Planned Action", plan.codecommit_repo_planned_operation)

    if plan.github_secret_name:
        console.print()
        print_kv("Installer GitHub Secret", plan.github_secret_name, bold_value=True)
        print_kv(
            "Secret Status",
            "EXISTS" if plan.github_secret_exists else "DOES NOT EXIST",
            bold_value=True,
        )
        print_kv(
            "GitHub Repository",
            f"{plan.github_repo_owner}/{plan.github_repo_name} ({plan.github_repo_branch})",
        )
        print_kv(
            "Repository Access",
            "ACCESSIBLE" if plan.github_repo_accessible else "NOT ACCESSIBLE",
            bold_value=True,
        )
        print_kv("Secret Planned Action", plan.github_planned_operation)

    console.print()
    op_color = (
        "green"
        if plan.planned_operation == "CREATE"
        else ("yellow" if plan.planned_operation in {"UPDATE", "WARNING"} else "blue")
    )
    print_kv(
        "Overall Planned Action",
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
    if dry_run or force or plan.planned_operation in {"NO_CHANGE", "WARNING"}:
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
    github_token: params.GithubToken = None,
    allow_missing_github_secret: params.AllowMissingGithubSecret = False,
) -> WorkspaceBootstrapResult | None:
    """Create or validate AWS prerequisite resources required by LZA Workbench."""
    resolved_github_token = github_token
    resolved_allow_missing = allow_missing_github_secret

    preparation = prepare_bootstrap_workflow(
        target_dir=target_dir,
        dry_run=dry_run,
        github_token=resolved_github_token,
        allow_missing_github_secret=resolved_allow_missing,
    )
    plan = preparation.plan

    # Interactive prompt if GitHub secret does not exist and no override was passed
    if (
        interactive
        and not dry_run
        and plan.github_secret_name
        and not plan.github_secret_exists
        and not resolved_github_token
        and not resolved_allow_missing
    ):
        console.print()
        print_notice(
            f"AWS Secrets Manager secret '{plan.github_secret_name}' "
            "does not exist in account/region."
        )
        provide_now = typer.confirm(
            "Would you like to provide a GitHub Personal Access Token now?",
            default=True,
        )
        if provide_now:
            resolved_github_token = typer.prompt(
                "Enter GitHub Personal Access Token",
                hide_input=True,
            )
            preparation = prepare_bootstrap_workflow(
                target_dir=target_dir,
                dry_run=dry_run,
                github_token=resolved_github_token,
                allow_missing_github_secret=resolved_allow_missing,
            )
            plan = preparation.plan
        else:
            proceed_anyway = typer.confirm(
                "Proceed anyway without creating the secret (you will need to create it manually)?",
                default=True,
            )
            if proceed_anyway:
                resolved_allow_missing = True
                preparation = prepare_bootstrap_workflow(
                    target_dir=target_dir,
                    dry_run=dry_run,
                    github_token=resolved_github_token,
                    allow_missing_github_secret=resolved_allow_missing,
                )
                plan = preparation.plan
            else:
                console.print("[dim]Bootstrap aborted by user.[/dim]")
                return None

    _render_bootstrap_plan(plan)

    if dry_run:
        console.print()
        print_dry_run_header("lza bootstrap")
        if plan.planned_operation == "NO_CHANGE":
            console.print(
                "[bold yellow]Dry run:[/bold yellow] all bootstrap prerequisite "
                "resources are already configured."
            )
        else:
            console.print(
                f"[bold yellow]Dry run:[/bold yellow] would execute "
                f"[bold green]{plan.planned_operation}[/bold green] for bootstrap "
                "prerequisite resources."
            )
        return None

    if not _confirm_bootstrap(plan=plan, dry_run=dry_run, force=force):
        return None

    console.print()
    print_info("Executing LZA Workbench bootstrap...", dim=True)
    result = apply_bootstrap_preparation(
        preparation=preparation,
        dry_run=False,
        github_token=resolved_github_token,
        allow_missing_github_secret=resolved_allow_missing,
    )

    console.print()
    print_notice(
        f"Bootstrap prerequisite resources are ready ({result.planned_operation})."
    )
    print_info(
        "Updated assets bucket in lza-workspace.yaml and operational state in .lza/state.json",
        dim=True,
    )
    for action in result.actions_taken:
        console.print(f"  ✓ {action}")

    if result.warnings:
        console.print()
        for warning in result.warnings:
            console.print(f"[bold yellow]WARNING:[/bold yellow] {warning}")

    return result


__all__ = [
    "BootstrapPlanResult",
    "WorkspaceBootstrapResult",
    "_confirm_bootstrap",
    "_render_bootstrap_plan",
    "workspace_bootstrap_command",
]
