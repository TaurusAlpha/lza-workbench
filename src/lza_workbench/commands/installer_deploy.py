"""Deploy the LZA installer CloudFormation stack for the current workspace."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from rich.panel import Panel
from rich.table import Table

from lza_workbench.aws.client_factory import AwsClientFactory
from lza_workbench.aws.cloudformation import (
    deploy_cloudformation_stack,
    inspect_cloudformation_stack,
    stream_cloudformation_stack_events,
)
from lza_workbench.aws.codecommit import (
    ensure_codecommit_repository,
    inspect_codecommit_repository,
)
from lza_workbench.aws.s3 import ensure_s3_installer_source
from lza_workbench.commands.installer_plan import (
    _gather_required_parameters,
    _inspect_template_parameters,
    _resolve_installer_template,
    _validate_parameters_against_schema,
)
from lza_workbench.core.errors import LzaError
from lza_workbench.installer.config import build_installer_cfn_parameters
from lza_workbench.utils.output import (
    console,
    print_info,
    print_kv,
    print_notice,
    print_section,
    print_warning,
)
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context
from lza_workbench.workspace.models import WorkspaceState
from lza_workbench.workspace.state import load_workspace_state, write_workspace_state


def run_installer_deploy(
    *,
    dry_run: bool = False,
    force: bool = False,
    target_dir: Path | None = None,
) -> None:
    """Deploy the LZA installer CloudFormation stack for the current workspace."""
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.CONFIGURED)
    workspace_dir, config, state = ctx.workspace_dir, ctx.config, ctx.state

    # 1. Check AWS configuration in lza-workspace.yaml
    profile = config.aws.profile or ""
    region = config.aws.region or "us-east-1"

    # 2. Pre-flight check: validate required installer parameters in configuration
    missing_specs = _gather_required_parameters(config)
    if missing_specs:
        console.print(
            "[bold red]Configuration error: missing required installer settings in"
            " lza-workspace.yaml:[/bold red]"
        )
        for spec in missing_specs:
            console.print(f"  - [bold]{spec.label}[/bold] ({spec.section}.{spec.attribute})")
        raise LzaError(
            f"{len(missing_specs)} required parameter(s) missing from lza-workspace.yaml. "
            "Run 'lza installer plan' to resolve and configure missing values."
        )

    # 3. AWS Client & Identity Validation
    try:
        factory = AwsClientFactory(profile=profile, region=region)
        aws_identity = factory.validate_identity()
    except Exception as exc:
        raise LzaError(f"AWS authentication check failed for profile '{profile}': {exc}") from exc

    # 4. Resolve Template & Validate Parameters
    template_path = _resolve_installer_template(workspace_dir, config, dry_run=dry_run)
    params_schema = _inspect_template_parameters(template_path)
    resolved_params = build_installer_cfn_parameters(config)
    _validate_parameters_against_schema(resolved_params, params_schema)

    # 5. Source Preparation Check (CodeCommit / S3)
    source_type = config.installer.source_code.repository_type
    if source_type == "codecommit":
        repo_name = config.installer.source_code.repository_name or "aws-accelerator-installer"
        branch_name = config.installer.source_code.branch or "main"
        cc_plan = inspect_codecommit_repository(
            factory=factory,
            repository_type=source_type,
            repository_name=repo_name,
            branch_name=branch_name,
            lza_version=config.lza.version,
            region=region,
        )
        if cc_plan.creation_required or cc_plan.sync_required:
            print_warning(
                f"Source repository '{repo_name}' (branch '{branch_name}') "
                "is missing or uninitialized."
            )
            if not force and not dry_run:
                confirm_source = typer.confirm(
                    f"Create and prepare CodeCommit repository '{repo_name}' automatically?",
                    default=True,
                )
                if not confirm_source:
                    console.print(
                        "[yellow]Source preparation cancelled by user. Halting deployment.[/yellow]"
                    )
                    return

            if not dry_run:
                print_info(f"Preparing CodeCommit repository '{repo_name}'...", dim=True)
                ensure_codecommit_repository(
                    factory=factory,
                    repository_name=repo_name,
                    branch_name=branch_name,
                )
                print_info(f"CodeCommit repository '{repo_name}' is ready.")

    elif source_type == "s3":
        bucket_name = (
            config.installer.source_code.owner
            or f"aws-accelerator-installer-{aws_identity['account']}-{region}"
        )
        if not dry_run:
            ensure_s3_installer_source(
                factory=factory,
                bucket_name=bucket_name,
                region=region,
            )

    # 6. CloudFormation Inspection
    stack_name = config.installer.stack_name or "AWSAccelerator-InstallerStack"
    cfn_plan = inspect_cloudformation_stack(
        factory=factory,
        stack_name=stack_name,
        resolved_parameters=resolved_params,
    )

    operation = cfn_plan.operation
    print_section(1, f"LZA Installer Stack Deployment ({operation})")
    print_kv("Stack Name", stack_name)
    print_kv("AWS Account", aws_identity["account"])
    print_kv("AWS Region", region)
    print_kv("AWS Profile", profile)
    print_kv("Operation", operation)
    if cfn_plan.stack_status:
        print_kv("Current Stack Status", cfn_plan.stack_status)

    console.print()
    if cfn_plan.parameter_diffs:
        diff_table = Table(title="Parameter Changes to be Applied", show_header=True)
        diff_table.add_column("Parameter Key", style="cyan")
        diff_table.add_column("Current Deployed Value", style="red")
        diff_table.add_column("Planned New Value", style="green")

        for k, (old_v, new_v) in sorted(cfn_plan.parameter_diffs.items()):
            diff_table.add_row(k, str(old_v), str(new_v))

        console.print(diff_table)
    else:
        param_table = Table(title="CloudFormation Parameters to be Deployed", show_header=True)
        param_table.add_column("Parameter Key", style="cyan")
        param_table.add_column("Value", style="white")

        for k, v in sorted(resolved_params.items()):
            param_table.add_row(k, str(v))

        console.print(param_table)

    console.print()

    if operation == "NO_CHANGE" and not force:
        print_info("No CloudFormation stack parameter changes detected. Stack is up to date.")
        confirm_redeploy = typer.confirm("Force re-deployment of stack?", default=False)
        if not confirm_redeploy:
            console.print("[dim]Deployment skipped as stack has no parameter changes.[/dim]")
            return

    # 7. Confirmation Prompt
    if not force and not dry_run:
        proceed = typer.confirm(
            f"Proceed with CloudFormation stack deployment ({operation}) for '{stack_name}'?",
            default=True,
        )
        if not proceed:
            console.print("[yellow]Deployment cancelled by user.[/yellow]")
            return

    if dry_run:
        console.print(
            Panel(
                f"[bold green]Dry-run complete.[/bold green]\n"
                f"Would execute CloudFormation [bold]{operation}[/bold] "
                f"for stack [bold]{stack_name}[/bold].\n"
                "No AWS resources were modified.",
                title="Dry Run Summary",
            )
        )
        return

    # 8. Deploy Stack & Stream Events
    template_body = template_path.read_text(encoding="utf-8")
    deploy_op = (
        "UPDATE"
        if cfn_plan.stack_status
        in {"CREATE_COMPLETE", "UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE"}
        else "CREATE"
    )

    print_info(f"Initiating CloudFormation stack {deploy_op}...", dim=True)
    stack_id = deploy_cloudformation_stack(
        factory=factory,
        stack_name=stack_name,
        template_body=template_body,
        parameters=resolved_params,
        operation=deploy_op,
    )
    print_info(f"Stack operation initiated (Stack ID: {stack_id}). Streaming events...", dim=True)

    def _render_evt(evt: dict[str, Any]) -> None:
        r_type = evt.get("ResourceType", "")
        r_id = evt.get("LogicalResourceId", "")
        r_status = evt.get("ResourceStatus", "")
        r_reason = evt.get("ResourceStatusReason", "")
        ts = str(evt.get("Timestamp", ""))[:19]
        reason_str = f" ({r_reason})" if r_reason else ""
        console.print(
            f"  [dim]{ts}[/dim] [bold]{r_id}[/bold] "
            f"({r_type}) -> [cyan]{r_status}[/cyan]{reason_str}"
        )

    final_status = stream_cloudformation_stack_events(
        factory=factory,
        stack_name=stack_name,
        on_event=_render_evt,
    )

    if final_status.stack_status in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}:
        print_notice(
            f"CloudFormation stack '{stack_name}' deployed successfully "
            f"({final_status.stack_status})."
        )

        # 9. Record State in .lza/state.json
        state_file = workspace_dir / ".lza" / "state.json"
        state = load_workspace_state(state_file) if state_file.exists() else WorkspaceState()
        state.management_account_id = aws_identity["account"]
        state.caller_arn = aws_identity["arn"]
        state.installer_stack_id = final_status.stack_id or stack_id
        state.installer_stack_status = final_status.stack_status
        state.installer_stack_updated_at = datetime.now(UTC)
        state.updated_at = datetime.now(UTC)
        write_workspace_state(state_file, state)
        print_info("Updated operational state in .lza/state.json", dim=True)

        # 10. Output & Extensible Next Steps
        if final_status.outputs:
            tbl = Table(title="Stack Outputs", show_header=True)
            tbl.add_column("Key", style="bold cyan")
            tbl.add_column("Value", style="green")
            for k, v in final_status.outputs.items():
                tbl.add_row(k, v)
            console.print(tbl)

        print_section(2, "Deployment Roadmap & Next Steps")
        console.print(
            "  [bold green]Phase 1 Complete:[/bold green] Installer CloudFormation stack deployed."
        )
        console.print(
            "  [bold yellow]Phase 2 Pending:[/bold yellow] AWS LZA Installer Pipeline execution."
        )
        console.print(
            "  [bold yellow]Phase 3 Pending:[/bold yellow] LZA Config Pipeline execution."
        )
        console.print()
        console.print("Recommended next commands:")
        console.print("  1. Upload LZA configuration: [bold code]lza config upload[/bold code]")
        console.print("  2. Monitor installer status: [bold code]lza installer status[/bold code]")
    else:
        console.print(
            f"[bold red]Deployment failed with stack status "
            f"({final_status.stack_status}).[/bold red]"
        )
        if final_status.error:
            console.print(f"[red]Error detail: {final_status.error}[/red]")
        raise LzaError(f"Deployment failed with stack status ({final_status.stack_status}).")
