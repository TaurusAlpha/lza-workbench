"""CLI command and presentation for adopting an existing LZA workspace."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.cli import params
from lza_workbench.cli.input import value_or_prompt
from lza_workbench.cli.output import (
    console,
    print_dry_run_header,
    print_kv,
    print_success,
)
from lza_workbench.workflows.workspace_import import (
    WorkspaceImportResult,
    discover_import_workspace,
    import_workspace_workflow,
)
from lza_workbench.workspace.paths import normalize_customer_slug
from lza_workbench.workspace.schema import LzaConfig


def render_workspace_import_result(result: WorkspaceImportResult) -> None:
    """Render the results of workspace import."""
    workspace_dir = result.workspace_dir
    config_dir = result.config_dir
    paths = result.affected_paths
    identity = result.identity
    provenance = result.provenance

    if result.dry_run:
        print_dry_run_header("lza import")
        print_kv("Workspace", workspace_dir)
        print_kv("Configuration", config_dir)
        if provenance and provenance.remote_url:
            print_kv("Git remote", provenance.remote_url)
            print_kv("Git branch", provenance.branch)
            if provenance.commit:
                print_kv("Git commit", provenance.commit)
        if result.repaired:
            console.print("[yellow]Mode:[/] Repair metadata")
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
        if result.discovered_stack_status:
            print_kv("Discovered installer stack", result.discovered_stack_status)
        if result.recommendations:
            console.print("\nNext steps:")
            for rec in result.recommendations:
                console.print(f"  - {rec}")
        return

    if result.repaired:
        print_success("Repaired and adopted LZA workspace")
    else:
        print_success("Imported LZA workspace")

    print_kv("Workspace", workspace_dir)
    print_kv("Configuration", config_dir)
    if provenance and provenance.remote_url:
        print_kv("Git remote", provenance.remote_url)
        print_kv("Git branch", provenance.branch)
        if provenance.commit:
            print_kv("Git commit", provenance.commit)
    if result.discovered_stack_status:
        print_kv("Discovered installer stack", result.discovered_stack_status)

    console.print("Affected paths:")
    for path in paths:
        console.print(f"  - {path}")
    if identity:
        print_kv("AWS account", identity["account"])
        print_kv("Caller ARN", identity["arn"])
    console.print("Customer configuration files were preserved.")

    if result.recommendations:
        console.print("\nNext steps:")
        for rec in result.recommendations:
            console.print(f"  - {rec}")


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
    repair: params.Repair = False,
    skip_aws_check: params.SkipAwsCheck = False,
    interactive: bool = False,
) -> None:
    """Adopt an existing customer-owned LZA configuration."""
    discovery = discover_import_workspace(
        workspace_dir=workspace_dir,
        config_dir=config_dir,
        force=force,
        repair=repair,
    )
    resolved_workspace_dir = discovery.workspace_dir
    existing = discovery.existing

    default_name = (
        existing.config.customer.name
        if existing and existing.config
        else resolved_workspace_dir.name
    )
    resolved_customer_name = value_or_prompt(
        "Customer name",
        customer_name,
        default_name,
        interactive,
    )
    customer_slug = (
        existing.config.customer.slug
        if existing and existing.config and existing.config.customer.name == resolved_customer_name
        else normalize_customer_slug(resolved_customer_name)
    )

    default_profile = (
        existing.config.aws.profile if existing and existing.config else f"{customer_slug}-root"
    )
    resolved_profile = value_or_prompt(
        "AWS profile",
        aws_profile or None,
        default_profile,
        interactive,
    )
    resolved_region = value_or_prompt(
        "AWS region",
        aws_region or None,
        existing.config.aws.region if existing and existing.config else "us-east-1",
        interactive,
    )
    resolved_version = value_or_prompt(
        "LZA version",
        lza_version,
        existing.config.lza.version if existing and existing.config else LzaConfig().version,
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
        repair=repair,
        skip_aws_check=skip_aws_check,
    )
    render_workspace_import_result(result)
