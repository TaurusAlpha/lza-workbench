"""CLI command handler and rendering for lza uninstall."""

from __future__ import annotations

import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import typer
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from lza_workbench.errors import LzaError
from lza_workbench.infrastructure.aws.session import (
    AwsExecutionContext,
    resolve_aws_execution_context,
)
from lza_workbench.interfaces.cli import params
from lza_workbench.interfaces.cli.output import (
    console,
    format_timestamp,
    print_dry_run_header,
    print_error,
    print_kv,
    print_success,
    render_workspace_header,
)
from lza_workbench.workspace.context import (
    WorkspaceCapability,
    WorkspaceContext,
    load_workspace_context,
)
from lza_workbench.workspace.uninstall.executor import execute_uninstall
from lza_workbench.workspace.uninstall.inventory import build_uninstall_plan
from lza_workbench.workspace.uninstall.models import (
    UninstallOptions,
    UninstallPlan,
    UninstallProgress,
)
from lza_workbench.workspace.uninstall.retained import (
    delete_selected_retained_resources,
    read_retained_resources_from_state,
)


def _render_inventory(plan: UninstallPlan, options: UninstallOptions) -> None:
    """Render a tabular overview of discovered stacks and resources."""
    console.print()
    console.print(f"[bold]Discovered AWS Accounts:[/bold] {len(plan.accounts)}")
    for acc in plan.accounts:
        role_info = f" (via role {acc.role_name})" if not acc.is_management and not acc.profile else ""
        prof_info = f" (profile: {acc.profile})" if acc.profile else ""
        mgmt_info = " [dim](Management Account)[/dim]" if acc.is_management else ""
        console.print(f"  - [cyan]{acc.account_id}[/cyan] ({acc.name}){mgmt_info}{prof_info}{role_info}")

    console.print()
    console.print(f"[bold]Target AWS Regions:[/bold] {', '.join(plan.regions)}")

    # Stacks Table
    console.print()
    stack_table = Table(
        title=f"CloudFormation Stacks to Delete ({plan.total_stacks} total, in reverse order)",
        show_header=True,
        header_style="bold magenta",
    )
    stack_table.add_column("#", style="dim", width=4)
    stack_table.add_column("Stack Name", style="bold")
    stack_table.add_column("Account ID")
    stack_table.add_column("Region")
    stack_table.add_column("Created", style="dim")
    stack_table.add_column("Protection")
    stack_table.add_column("Retained Res.", justify="right")

    for idx, s in enumerate(plan.stacks, 1):
        prot_str = "[bold red]ENABLED[/bold red]" if s.termination_protection else "[green]No[/green]"
        created_str = format_timestamp(s.creation_time) or "Unknown"
        retained_count = str(len(s.retained_resources)) if s.retained_resources else "-"
        stack_table.add_row(
            str(idx),
            s.stack_name,
            s.account_id,
            s.region,
            created_str,
            prot_str,
            retained_count,
        )

    console.print(stack_table)

    # S3 Buckets summary
    if plan.s3_buckets:
        console.print()
        bucket_table = Table(
            title=f"Discovered LZA S3 Buckets ({plan.total_s3_buckets} total)",
            show_header=True,
            header_style="bold cyan",
        )
        bucket_table.add_column("Bucket Name", style="bold")
        bucket_table.add_column("Account ID")
        bucket_table.add_column("Region")
        bucket_table.add_column("Policy Action")

        bucket_action = "[bold red]EMPTY & DELETE[/bold red]" if options.delete_s3_buckets else "[green]RETAIN (Preserved)[/green]"
        for b in plan.s3_buckets:
            bucket_table.add_row(b.bucket_name, b.account_id, b.region, bucket_action)
        console.print(bucket_table)

    # Retained Resources breakdown
    if plan.retained_resources:
        console.print()
        counts = Counter(r.resource_type for r in plan.retained_resources)
        res_table = Table(
            title=f"Resources with DeletionPolicy: Retain ({plan.total_retained_resources} total)",
            show_header=True,
            header_style="bold yellow",
        )
        res_table.add_column("Resource Type", style="bold")
        res_table.add_column("Count", justify="right")
        res_table.add_column("Action")

        retained_action = "[bold red]FORCE DELETE[/bold red]" if options.delete_retained_resources else "[green]RETAIN (Preserved)[/green]"
        for res_type, count in counts.most_common():
            res_table.add_row(res_type, str(count), retained_action)
        console.print(res_table)


def _confirm_uninstall_interactive(context: WorkspaceContext, plan: UninstallPlan) -> None:
    """Show destruction warning and require typing the customer slug to proceed."""
    if not sys.stdin.isatty():
        raise LzaError("Interactive confirmation required. Pass --force to execute non-interactively.")

    console.print()
    console.print(
        Panel(
            f"[bold red]WARNING: Destructive Operation![/bold red]\n\n"
            f"You are about to delete [bold]{plan.total_stacks}[/bold] CloudFormation stacks across "
            f"[bold]{len(plan.accounts)}[/bold] accounts and [bold]{len(plan.regions)}[/bold] regions.\n"
            f"Termination protection will be disabled automatically on protected stacks.\n\n"
            f"Customer: [bold cyan]{context.config.customer.name}[/bold cyan] (slug: [bold yellow]{context.config.customer.slug}[/bold yellow])",
            border_style="red",
        )
    )

    confirm_slug = typer.prompt(
        f"To confirm deletion, type customer slug '{context.config.customer.slug}'",
        default="",
    )
    if confirm_slug.strip() != context.config.customer.slug:
        console.print("[yellow]Teardown aborted. Slug confirmation did not match.[/yellow]")
        raise typer.Exit(code=1)


def _handle_interactive_post_cleanup(
    context: WorkspaceContext,
    execution_context: AwsExecutionContext,
    plan: UninstallPlan,
    options: UninstallOptions,
    on_event: Callable[[str, str], None] | None = None,
) -> None:
    """Prompt to delete S3 buckets and retained resources if not already selected."""
    if not sys.stdin.isatty():
        return

    if not options.delete_s3_buckets and plan.s3_buckets:
        console.print()
        if Confirm.ask(
            f"Discovered {len(plan.s3_buckets)} LZA S3 buckets. Do you want to empty and delete them now?",
            default=False,
        ):
            opt_buckets = UninstallOptions(
                delete_s3_buckets=True,
                assume_role_name=options.assume_role_name,
            )
            execute_uninstall(
                context=context,
                execution_context=execution_context,
                plan=plan,
                options=opt_buckets,
                on_event=on_event,
            )

    if not options.delete_retained_resources and plan.retained_resources:
        console.print()
        if Confirm.ask(
            f"Discovered {len(plan.retained_resources)} retained resources (LogGroups, KMS keys, etc.) recorded in state. Do you want to force-delete them now?",
            default=False,
        ):
            delete_selected_retained_resources(
                context=context,
                execution_context=execution_context,
                account_targets=plan.accounts,
                assume_role_name=options.assume_role_name,
                on_event=on_event,
            )


def _render_final_summary(progress: UninstallProgress, context: WorkspaceContext) -> None:
    """Render the final operation summary with counts and audit log paths."""
    retained_in_state = read_retained_resources_from_state(context)
    deleted_retained_count = sum(1 for r in retained_in_state if r.status == "deleted")
    preserved_retained_count = sum(1 for r in retained_in_state if r.status != "deleted")

    console.print()
    if progress.status == "COMPLETED":
        print_success("LZA Solution Uninstallation Completed")
    else:
        print_error("LZA Solution Uninstallation Completed with Failures")

    print_kv("Deleted Stacks", len(progress.deleted_stacks))
    if progress.failed_stacks:
        print_kv("Failed Stacks", len(progress.failed_stacks), style="bold red")
    if progress.deleted_buckets:
        print_kv("Deleted S3 Buckets", len(progress.deleted_buckets), style="green")
    if deleted_retained_count:
        print_kv("Deleted Retained Resources", deleted_retained_count, style="green")
    if preserved_retained_count:
        print_kv("Preserved Retained Resources in State", preserved_retained_count, style="yellow")

    progress_file = context.state_dir / "uninstall-progress.json"
    print_kv("Uninstall Audit Log", progress_file)
    print_kv("Workspace State", context.state_file)


def uninstall_command(
    workspace_dir: Path | None = None,
    regions: params.UninstallRegions = None,
    all_regions: params.UninstallAllRegions = False,
    accounts: params.UninstallAccounts = None,
    assume_role_name: params.AssumeRoleName = "AWSAccelerator-PipelineRole",
    profiles_file: params.ProfilesFile = None,
    delete_s3_buckets: params.DeleteS3Buckets = False,
    delete_retained_resources: params.DeleteRetainedResources = False,
    skip_installer: params.SkipInstaller = False,
    skip_pipeline: params.SkipPipeline = False,
    dry_run: params.DryRun = False,
    force: params.Force = False,
    interactive: bool = True,
) -> None:
    """Uninstall the LZA solution across managed accounts and regions."""
    context = load_workspace_context(
        target_dir=workspace_dir,
        required_capabilities=(WorkspaceCapability.METADATA_VALID,),
    )

    execution_context = resolve_aws_execution_context(
        profile=context.config.aws.profile,
        region=context.config.aws.region,
        role_arn=context.config.aws.role_arn,
        expected_account_id=context.config.aws.account_id,
        prime_credentials=context.config.aws.prime_credentials,
        validate_identity=True,
        require_identity=True,
    )

    render_workspace_header(
        "LZA Solution Uninstallation",
        customer_name=context.config.customer.name,
        workspace_dir=context.workspace_dir,
        lza_version=context.config.lza.version,
        profile=context.config.aws.profile,
        region=context.config.aws.region,
        aws_identity=execution_context.identity,
    )

    parsed_regions = [r.strip() for r in regions.split(",") if r.strip()] if regions else []
    parsed_accounts = [a.strip() for a in accounts.split(",") if a.strip()] if accounts else []

    options = UninstallOptions(
        dry_run=dry_run,
        force=force,
        regions=parsed_regions,
        all_regions=all_regions,
        accounts=parsed_accounts,
        assume_role_name=assume_role_name,
        profiles_file=profiles_file,
        delete_s3_buckets=delete_s3_buckets,
        delete_retained_resources=delete_retained_resources,
        skip_installer=skip_installer,
        skip_pipeline=skip_pipeline,
    )

    console.print("\n[bold cyan]Phase 1: Discovering LZA resources...[/bold cyan]")
    plan = build_uninstall_plan(
        context=context,
        execution_context=execution_context,
        options=options,
    )

    _render_inventory(plan, options)

    if options.dry_run:
        print_dry_run_header("lza uninstall")
        console.print("[dim]Dry run complete. No AWS resources or configuration files were changed.[/dim]")
        return

    if plan.total_stacks == 0 and plan.total_s3_buckets == 0:
        print_success("No deployed LZA stacks or resources discovered. Nothing to delete.")
        return

    if not options.force:
        _confirm_uninstall_interactive(context, plan)

    console.print("\n[bold cyan]Phase 2: Executing teardown in reverse deployment order...[/bold cyan]")

    def on_event(event_type: str, message: str) -> None:
        if event_type == "delete_stack":
            console.print(f"  [yellow]→[/yellow] {message}...")
        elif event_type == "stack_deleted":
            console.print(f"    [green]✓[/green] {message}")
        elif event_type == "stack_failed":
            console.print(f"    [bold red]✗[/bold red] {message}")
        elif event_type in ("protect", "delete_bucket", "delete_retained"):
            console.print(f"  [dim]• {message}[/dim]")

    progress = execute_uninstall(
        context=context,
        execution_context=execution_context,
        plan=plan,
        options=options,
        on_event=on_event,
    )

    if interactive and not options.force:
        _handle_interactive_post_cleanup(context, execution_context, plan, options, on_event)

    _render_final_summary(progress, context)


__all__ = ["uninstall_command"]
