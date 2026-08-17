"""CLI command and presentation for initializing a customer workspace."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.cli import params
from lza_workbench.cli.presentation import (
    console,
    print_dry_run_header,
    print_kv,
    print_success,
    value_or_prompt,
)
from lza_workbench.workflows.workspace_init import (
    WorkspaceInitResult,
    init_workspace_workflow,
)
from lza_workbench.workspace.paths import normalize_customer_slug, resolve_init_workspace_dir
from lza_workbench.workspace.schema import LzaConfig


def render_workspace_init_result(result: WorkspaceInitResult) -> None:
    """Render the results of workspace initialization."""
    workspace_dir = result.workspace_dir
    config = result.config
    identity = result.identity

    if result.dry_run:
        print_dry_run_header("lza init")
        print_kv("Workspace", workspace_dir)
        print_kv("Template", config.configuration.template.name)
        console.print("Planned writes:")
        for path in result.planned_paths:
            console.print(f"  - {path}")
        if identity:
            print_kv("AWS account", identity["account"])
            print_kv("Caller ARN", identity["arn"])
        return

    print_success("Initialized LZA workspace")
    print_kv("Workspace", workspace_dir)
    print_kv("Customer", f"{config.customer.name} ({config.customer.slug})")
    if config.aws.profile:
        print_kv("AWS profile", config.aws.profile)
    print_kv("AWS region", config.aws.region)
    print_kv("LZA version", config.lza.version)
    if identity:
        print_kv("AWS account", identity["account"])
        print_kv("Caller ARN", identity["arn"])


def workspace_init_command(
    *,
    customer_name: params.CustomerName,
    workspace_dir: params.WorkspaceDir = None,
    aws_auth_type: params.AwsAuthType = "profile",
    aws_profile: params.AwsProfile = "",
    aws_region: params.AwsRegion = "",
    lza_version: params.LzaVersion = None,
    dry_run: params.DryRun = False,
    force: params.Force = False,
    skip_aws_check: params.SkipAwsCheck = True,
    interactive: bool = False,
) -> None:
    """Create a customer workspace using the configured packaged template."""
    customer_slug = normalize_customer_slug(customer_name)
    default_workspace_dir = resolve_init_workspace_dir(customer_name)

    if workspace_dir is None:
        resolved_ws_dir = (
            Path(
                value_or_prompt(
                    "Workspace directory",
                    None,
                    str(default_workspace_dir),
                    interactive,
                )
            )
            .expanduser()
            .resolve()
        )
    else:
        resolved_ws_dir = resolve_init_workspace_dir(customer_name, workspace_dir)

    resolved_profile = value_or_prompt(
        "AWS profile", aws_profile or None, f"{customer_slug}-root", interactive
    )
    resolved_region = value_or_prompt("AWS region", aws_region or None, "us-east-1", interactive)
    resolved_version = value_or_prompt(
        "LZA version", lza_version, LzaConfig().version, interactive
    )

    result = init_workspace_workflow(
        customer_name=customer_name,
        workspace_dir=resolved_ws_dir,
        aws_auth_type=aws_auth_type,
        aws_profile=resolved_profile,
        aws_region=resolved_region,
        lza_version=resolved_version,
        dry_run=dry_run,
        force=force,
        skip_aws_check=skip_aws_check,
    )
    render_workspace_init_result(result)
