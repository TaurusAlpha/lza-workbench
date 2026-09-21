"""CLI commands and presentation for workspace lifecycle."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.interfaces.cli import params
from lza_workbench.interfaces.cli.input import value_or_prompt
from lza_workbench.interfaces.cli.output import (
    console,
    print_dry_run_header,
    print_kv,
    print_success,
)
from lza_workbench.workspace.import_workspace import (
    ImportWorkspaceRequest,
    WorkspaceImportResult,
    apply_workspace_import,
    discover_import_workspace,
    prepare_workspace_import,
)
from lza_workbench.workspace.initialize import (
    WorkspaceInitResult,
    init_workspace,
)
from lza_workbench.workspace.paths import (
    normalize_customer_slug,
    resolve_init_workspace_dir,
)
from lza_workbench.workspace.schema import LzaConfig


def render_workspace_init_result(result: WorkspaceInitResult) -> None:
    workspace_dir = result.workspace_dir
    config = result.config
    identity = result.identity

    if result.dry_run:
        print_dry_run_header("lza init")
        print_kv("Workspace", workspace_dir)
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
    if config.aws.role_arn:
        print_kv("AWS role ARN", config.aws.role_arn)
    print_kv("AWS region", config.aws.region)
    print_kv("LZA version", config.lza.version)
    if identity:
        print_kv("AWS account", identity["account"])
        print_kv("Caller ARN", identity["arn"])

    console.print()
    console.print("[bold]Next steps:[/bold]")
    console.print(f"  1. [cyan]cd {workspace_dir}[/cyan] - Change to the workspace directory")
    console.print(
        "  2. [cyan]lza installer init[/cyan]  - Configure installer parameters and account emails"
    )
    console.print(
        "  3. [cyan]lza config init[/cyan]     - Initialize local LZA configuration from template"
    )


def workspace_init_command(
    *,
    customer_name: params.CustomerName,
    workspace_dir: params.WorkspaceDir = None,
    aws_auth_type: params.AwsAuthType = "profile",
    aws_profile: params.AwsProfile = "",
    aws_role_arn: params.AwsRoleArn = "",
    aws_region: params.AwsRegion = "",
    lza_version: params.LzaVersion = None,
    dry_run: params.DryRun = False,
    force: params.Force = False,
    skip_aws_check: params.SkipAwsCheck = False,
    interactive: bool = False,
) -> None:
    customer_slug = normalize_customer_slug(customer_name)
    default_workspace_dir = resolve_init_workspace_dir(customer_slug)

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
        resolved_ws_dir = resolve_init_workspace_dir(customer_slug, workspace_dir)

    if aws_auth_type == "role_arn":
        resolved_role_arn = value_or_prompt("AWS role ARN", aws_role_arn or None, None, interactive)
        resolved_profile = aws_profile.strip() or None if aws_profile else None
    else:
        resolved_profile = value_or_prompt(
            "AWS profile", aws_profile or None, f"{customer_slug}-root", interactive
        )
        resolved_role_arn = aws_role_arn.strip() or None if aws_role_arn else None

    resolved_region = value_or_prompt("AWS region", aws_region or None, "us-east-1", interactive)
    resolved_version = value_or_prompt("LZA version", lza_version, LzaConfig().version, interactive)

    result = init_workspace(
        customer_name=customer_name,
        workspace_dir=resolved_ws_dir,
        aws_auth_type=aws_auth_type,
        aws_profile=resolved_profile,
        aws_role_arn=resolved_role_arn,
        aws_region=resolved_region,
        lza_version=resolved_version,
        dry_run=dry_run,
        force=force,
        skip_aws_check=skip_aws_check,
    )
    render_workspace_init_result(result)


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
