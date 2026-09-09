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
    ImportWorkspaceRequest,
    WorkspaceImportResult,
    apply_workspace_import,
    discover_import_workspace,
    prepare_workspace_import,
)
from lza_workbench.workspace.paths import normalize_customer_slug
from lza_workbench.workspace.schema import LzaConfig


def _render_import_provenance(result: WorkspaceImportResult) -> None:
    provenance = result.provenance
    if not provenance or not provenance.remote_url:
        return
    print_kv("Git remote", provenance.remote_url)
    print_kv("Git branch", provenance.branch)
    if provenance.commit:
        print_kv("Git commit", provenance.commit)


def _render_affected_paths(result: WorkspaceImportResult) -> None:
    console.print("Affected paths:")
    for path in result.affected_paths:
        console.print(f"  - {path}")


def _render_import_identity(result: WorkspaceImportResult) -> None:
    if result.identity:
        print_kv("AWS account", result.identity["account"])
        print_kv("Caller ARN", result.identity["arn"])


def _render_recommendations(result: WorkspaceImportResult) -> None:
    if not result.recommendations:
        return
    console.print("\nNext steps:")
    for recommendation in result.recommendations:
        console.print(f"  - {recommendation}")


def _render_import_location(result: WorkspaceImportResult) -> None:
    print_kv("Workspace", result.workspace_dir)
    print_kv("Configuration", result.config_dir)
    _render_import_provenance(result)


def _render_import_details(
    result: WorkspaceImportResult,
    *,
    include_discovered_stack: bool,
) -> None:
    _render_import_location(result)
    if include_discovered_stack and result.discovered_stack_status:
        print_kv("Discovered installer stack", result.discovered_stack_status)
    _render_affected_paths(result)
    _render_import_identity(result)
    console.print("Customer configuration files were preserved.")


def render_workspace_import_result(result: WorkspaceImportResult) -> None:
    """Render the results of workspace import."""
    if result.dry_run:
        print_dry_run_header("lza import")
        _render_import_location(result)
        if result.repaired:
            console.print("[yellow]Mode:[/] Repair metadata")
        _render_affected_paths(result)
        _render_import_identity(result)
        console.print("Customer configuration files were preserved.")
        return

    if result.already_imported:
        print_success("Workspace already imported; no metadata changes")
        if result.discovered_stack_status:
            print_kv("Discovered installer stack", result.discovered_stack_status)
        _render_recommendations(result)
        return

    print_success(
        "Repaired and adopted LZA workspace" if result.repaired else "Imported LZA workspace"
    )
    _render_import_details(result, include_discovered_stack=True)
    _render_recommendations(result)


def workspace_import_command(
    *,
    workspace_dir: params.ImportWorkspaceDir = Path("."),
    customer_name: params.ImportCustomerName = None,
    config_dir: params.LzaConfigDir = None,
    aws_auth_type: params.AwsAuthType = "profile",
    aws_profile: params.AwsProfile = "",
    aws_region: params.AwsRegion = "",
    lza_version: params.LzaVersion = None,
    installer_stack_name: params.InstallerStackName = None,
    dry_run: params.DryRun = False,
    force: params.Force = False,
    repair: params.Repair = False,
    skip_aws_check: params.SkipAwsCheck = False,
    prime_credentials: params.PrimeCredentials = False,
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
    default_stack_name = (
        existing.config.installer.stack_name
        if existing and existing.config and existing.config.installer.stack_name
        else "AWSAccelerator-InstallerStack"
    )
    resolved_stack_name = value_or_prompt(
        "Installer stack name",
        installer_stack_name,
        default_stack_name,
        interactive,
    )

    preparation = prepare_workspace_import(
        ImportWorkspaceRequest(
            workspace_dir=workspace_dir,
            config_dir=config_dir,
            customer_name=resolved_customer_name,
            aws_auth_type=aws_auth_type,
            aws_profile=resolved_profile,
            aws_region=resolved_region,
            lza_version=resolved_version,
            installer_stack_name=resolved_stack_name,
            dry_run=dry_run,
            force=force,
            repair=repair,
            skip_aws_check=skip_aws_check,
            prime_credentials=prime_credentials,
            discovery=discovery,
        )
    )
    result = apply_workspace_import(preparation)
    render_workspace_import_result(result)
