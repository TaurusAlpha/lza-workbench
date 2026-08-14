"""Resolve and persist installer configuration and plan LZA deployment actions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.panel import Panel
from rich.table import Table

from lza_workbench.aws.cloudformation import (
    CfnDeploymentPlanResult,
    inspect_cloudformation_stack,
)
from lza_workbench.aws.codecommit import (
    CodeCommitPlanResult,
    inspect_codecommit_repository,
)
from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.core.errors import LzaError
from lza_workbench.core.installer_template import (
    INSTALLER_TEMPLATE_FILENAME,
    download_installer_template,
)
from lza_workbench.installer.config import validate_installer_configuration
from lza_workbench.installer.parameters import build_installer_cfn_parameters
from lza_workbench.utils.output import (
    console,
    print_info,
    print_kv,
    print_notice,
    print_section,
    print_warning,
)
from lza_workbench.workspace.config import write_workspace_config
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context
from lza_workbench.workspace.models import WorkspaceConfig


def run_installer_plan(
    *,
    dry_run: bool = False,
    no_save: bool = False,
    target_dir: Path | None = None,
) -> None:
    """Resolve installer config from workspace and show planned deployment actions."""
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.CONFIGURED)
    workspace_dir, config = ctx.workspace_dir, ctx.config

    profile = config.aws.profile or ""

    # Validate required installer configuration parameters in workspace
    validation = validate_installer_configuration(config)
    if not validation.is_complete:
        console.print(
            "[bold red]Configuration error: missing required installer settings in "
            "lza-workspace.yaml:[/bold red]"
        )
        for spec in validation.missing_fields:
            console.print(f"  - [bold]{spec.label}[/bold] ({spec.section}.{spec.attribute})")
        raise LzaError(
            f"{len(validation.missing_fields)} required parameter(s) missing from "
            "lza-workspace.yaml. "
            "Update lza-workspace.yaml with required values."
        )

    # Save accepted installer settings if requested and not dry run
    if not no_save and not dry_run:
        write_workspace_config(workspace_dir, config)
        print_info("Installer configuration verified in lza-workspace.yaml", dim=True)

    # Step 1: Template Resolution & Parameter Schema Inspection
    template_path = _resolve_installer_template(workspace_dir, config, dry_run=dry_run)
    params_schema = _inspect_template_parameters(template_path)

    # Step 2: Validate Resolved Parameters against Template Schema
    resolved_params = build_installer_cfn_parameters(config)
    _validate_parameters_against_schema(resolved_params, params_schema)

    # Step 3: Create AWS Factory & Validate Profile Identity
    aws_context = resolve_aws_execution_context(config.aws)
    factory = aws_context.factory
    region = aws_context.region
    aws_identity = aws_context.identity
    aws_error = aws_context.error

    # Step 4: CodeCommit Source Planning
    codecommit_client = factory.get_client("codecommit") if aws_identity else None
    codecommit_plan = inspect_codecommit_repository(
        client=codecommit_client,
        repository_type=config.installer.source_code.repository_type,
        repository_name=config.installer.source_code.repository_name,
        branch_name=config.installer.source_code.branch,
        lza_version=config.lza.version,
        region=region,
    )

    # Step 5: CloudFormation Deployment Planning
    stack_name = config.installer.stack_name or "AWSAccelerator-InstallerStack"
    cfn_client = factory.get_client("cloudformation") if aws_identity else None
    cfn_plan = inspect_cloudformation_stack(
        client=cfn_client,
        stack_name=stack_name,
        resolved_parameters=resolved_params,
    )

    # Step 6: Render Read-Only Summary Plan Report
    _render_plan_report(
        workspace_dir=workspace_dir,
        config=config,
        profile=profile,
        region=region,
        aws_identity=aws_identity,
        aws_error=aws_error,
        codecommit_plan=codecommit_plan,
        cfn_plan=cfn_plan,
        dry_run=dry_run,
    )


def _resolve_installer_template(
    workspace_dir: Path, config: WorkspaceConfig, dry_run: bool
) -> Path:
    """Locate local template or download it into installer local directory."""
    installer_dir = workspace_dir / config.installer.local_path
    template_path = installer_dir / INSTALLER_TEMPLATE_FILENAME

    if not template_path.exists():
        if dry_run:
            print_info(
                f"Template {INSTALLER_TEMPLATE_FILENAME} not found locally. "
                "Would download during execution.",
                dim=True,
            )
            packaged = Path(__file__).parent.parent / "config" / INSTALLER_TEMPLATE_FILENAME
            if packaged.exists():
                return packaged
            return template_path

        ver = config.lza.version
        print_notice(f"Downloading LZA installer template ({ver})...")
        template_path = download_installer_template(
            version=config.lza.version,
            local_path=template_path,
        )

    return template_path


def _inspect_template_parameters(template_path: Path) -> dict[str, dict[str, Any]]:
    """Parse JSON template and extract parameter schema definitions."""
    if not template_path.exists():
        return {}

    try:
        data = json.loads(template_path.read_text(encoding="utf-8"))
        return data.get("Parameters", {})
    except (OSError, json.JSONDecodeError):
        return {}


def _validate_parameters_against_schema(
    resolved_params: dict[str, str], schema: dict[str, dict[str, Any]]
) -> None:
    """Validate resolved parameter values against CloudFormation template schema."""
    if not schema:
        return

    for key, value in resolved_params.items():
        if key not in schema:
            continue

        param_def = schema[key]
        allowed = param_def.get("AllowedValues")
        if allowed and value not in allowed:
            raise LzaError(
                f"Invalid parameter value '{value}' for {key}. "
                f"Allowed values are: {', '.join(allowed)}"
            )


def _render_plan_report(
    *,
    workspace_dir: Path,
    config: WorkspaceConfig,
    profile: str,
    region: str,
    aws_identity: dict[str, str] | None,
    aws_error: str | None,
    codecommit_plan: CodeCommitPlanResult,
    cfn_plan: CfnDeploymentPlanResult,
    dry_run: bool,
) -> None:
    """Render structured rich summary plan output for the user."""
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
