"""Initialize a customer workspace from the default workspace configuration."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from lza_workbench.aws.identity import validate_aws_profile
from lza_workbench.core.templates import resolve_template_source, validate_template
from lza_workbench.core.workspace import (
    AwsConfig,
    CustomerConfig,
    LzaConfig,
    WorkspaceConfig,
    WorkspaceState,
    create_workspace,
    normalize_customer_slug,
    planned_write_paths,
    validate_workspace_target,
)

console = Console()


def run_init(
    *,
    customer_name: str,
    workspace_dir: Path,
    aws_profile: str | None,
    aws_region: str | None,
    lza_version: str | None,
    dry_run: bool,
    force: bool,
    skip_aws_check: bool,
    interactive: bool,
) -> None:
    """Create a customer workspace using the configured packaged template."""
    customer_slug = normalize_customer_slug(customer_name)
    config = build_workspace_config(
        customer_name=customer_name,
        customer_slug=customer_slug,
        aws_profile=_value_or_prompt("AWS profile", aws_profile, customer_slug, interactive),
        aws_region=_value_or_prompt("AWS region", aws_region, AwsConfig().region, interactive),
        lza_version=_value_or_prompt("LZA version", lza_version, LzaConfig().version, interactive),
    )
    template_dir = resolve_packaged_template(config)

    validate_template(template_dir)
    validate_workspace_target(workspace_dir, force)

    if skip_aws_check:
        identity = None
    else:
        identity = validate_aws_profile(config.aws.profile or "", config.aws.region)

    if dry_run:
        print_dry_run_summary(workspace_dir, config, identity)
        return

    create_workspace(
        workspace_dir=workspace_dir,
        template_config_dir=template_dir,
        config=config,
        state=WorkspaceState.from_config(config),
    )
    validate_template(workspace_dir / config.configuration.local_path)
    print_success_summary(workspace_dir, config, identity)


def build_workspace_config(
    *,
    customer_name: str,
    customer_slug: str,
    aws_profile: str,
    aws_region: str,
    lza_version: str,
) -> WorkspaceConfig:
    """Build init configuration; future CLI overrides belong here."""
    return WorkspaceConfig(
        customer=CustomerConfig(name=customer_name, slug=customer_slug),
        aws=AwsConfig(profile=aws_profile, region=aws_region),
        lza=LzaConfig(version=lza_version),
    )


def resolve_packaged_template(config: WorkspaceConfig) -> Path:
    """Resolve the packaged template selected by the workspace defaults."""
    template = config.configuration.template
    if template.source != "packaged" or template.name is None:
        raise ValueError("Init requires a named packaged configuration template.")
    return resolve_template_source(template.name).config_dir


def print_dry_run_summary(
    workspace_dir: Path,
    config: WorkspaceConfig,
    identity: dict[str, str] | None,
) -> None:
    console.print("[bold]Dry run: lza init[/bold]")
    console.print(f"Workspace: {workspace_dir}")
    console.print(f"Template: {config.configuration.template.name}")
    console.print("Planned writes:")
    for path in planned_write_paths(workspace_dir, config):
        console.print(f"  - {path}")
    if identity:
        console.print(f"AWS account: {identity['account']}")
        console.print(f"Caller ARN: {identity['arn']}")


def print_success_summary(
    workspace_dir: Path,
    config: WorkspaceConfig,
    identity: dict[str, str] | None,
) -> None:
    console.print("[bold green]Initialized LZA workspace[/bold green]")
    console.print(f"Workspace: {workspace_dir}")
    console.print(f"Customer: {config.customer.name} ({config.customer.slug})")
    console.print(f"AWS profile: {config.aws.profile}")
    console.print(f"AWS region: {config.aws.region}")
    console.print(f"LZA version: {config.lza.version}")
    if identity:
        console.print(f"AWS account: {identity['account']}")
        console.print(f"Caller ARN: {identity['arn']}")


def _value_or_prompt(label: str, value: str | None, default: str, interactive: bool) -> str:
    if value:
        return value
    if interactive:
        return typer.prompt(label, default=default)
    return default
