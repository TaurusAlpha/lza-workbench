"""CLI command and presentation for adopting an existing LZA workspace."""

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
from lza_workbench.workflows.workspace_import import (
    WorkspaceImportResult,
    import_workspace_workflow,
    load_existing_metadata,
    resolve_import_paths,
)
from lza_workbench.workspace.paths import normalize_customer_slug
from lza_workbench.workspace.schema import LzaConfig


def render_workspace_import_result(result: WorkspaceImportResult) -> None:
    """Render the results of workspace import."""
    workspace_dir = result.workspace_dir
    config_dir = result.config_dir
    paths = result.affected_paths
    identity = result.identity

    if result.dry_run:
        print_dry_run_header("lza import")
        print_kv("Workspace", workspace_dir)
        print_kv("Configuration", config_dir)
        console.print("Affected paths:")
        for path in paths:
            console.print(f"  - {path}")
        if identity:
            print_kv("AWS account", identity["account"])
            print_kv("Caller ARN", identity["arn"])
        console.print("Customer configuration files were preserved.")
        return

    if result.already_imported:
        print_success("Workspace already imported; no metadata changes")
        return

    print_success("Imported LZA workspace")
    print_kv("Workspace", workspace_dir)
    print_kv("Configuration", config_dir)
    console.print("Affected paths:")
    for path in paths:
        console.print(f"  - {path}")
    if identity:
        print_kv("AWS account", identity["account"])
        print_kv("Caller ARN", identity["arn"])
    console.print("Customer configuration files were preserved.")


def workspace_import_command(
    *,
    workspace_dir: params.ImportWorkspaceDir = Path("."),
    customer_name: params.ImportCustomerName = None,
    config_dir: params.LzaConfigDir = None,
    aws_auth_type: params.AwsAuthType = "profile",
    aws_profile: params.AwsProfile = "",
    aws_region: params.AwsRegion = "",
    lza_version: params.LzaVersion = None,
    dry_run: params.DryRun = False,
    force: params.Force = False,
    skip_aws_check: params.SkipAwsCheck = False,
    interactive: bool = False,
) -> None:
    """Adopt an existing customer-owned LZA configuration."""
    resolved_workspace_dir, _ = resolve_import_paths(
        workspace_dir=workspace_dir,
        config_dir=config_dir,
    )
    existing = load_existing_metadata(resolved_workspace_dir, force=force)

    resolved_customer_name = value_or_prompt(
        "Customer name",
        customer_name,
        existing.config.customer.name if existing else resolved_workspace_dir.name,
        interactive,
    )
    customer_slug = (
        existing.config.customer.slug
        if existing and existing.config.customer.name == resolved_customer_name
        else normalize_customer_slug(resolved_customer_name)
    )

    resolved_profile = value_or_prompt(
        "AWS profile",
        aws_profile or None,
        existing.config.aws.profile if existing else f"{customer_slug}-root",
        interactive,
    )
    resolved_region = value_or_prompt(
        "AWS region",
        aws_region or None,
        existing.config.aws.region if existing else "us-east-1",
        interactive,
    )
    resolved_version = value_or_prompt(
        "LZA version",
        lza_version,
        existing.config.lza.version if existing else LzaConfig().version,
        interactive,
    )

    result = import_workspace_workflow(
        workspace_dir=workspace_dir,
        config_dir=config_dir,
        customer_name=resolved_customer_name,
        aws_auth_type=aws_auth_type,
        aws_profile=resolved_profile,
        aws_region=resolved_region,
        lza_version=resolved_version,
        dry_run=dry_run,
        force=force,
        skip_aws_check=skip_aws_check,
    )
    render_workspace_import_result(result)
