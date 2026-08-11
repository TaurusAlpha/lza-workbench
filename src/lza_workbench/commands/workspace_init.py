"""Initialize a customer workspace from the default workspace configuration."""

from __future__ import annotations

from pathlib import Path

import typer

from lza_workbench.aws.client_factory import validate_aws_credentials
from lza_workbench.core.errors import LzaError
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
from lza_workbench.utils.output import (
    console,
    print_dry_run_header,
    print_kv,
    print_success,
)


def run_init(
    *,
    customer_name: str,
    workspace_dir: Path,
    aws_auth_type: str = "profile",
    aws_profile: str | None = None,
    aws_role: str | None = None,
    aws_access_key: str | None = None,
    aws_secret_key: str | None = None,
    aws_region: str | None = None,
    lza_version: str | None = None,
    dry_run: bool,
    force: bool,
    skip_aws_check: bool,
    interactive: bool,
) -> None:
    """Create a customer workspace using the configured packaged template."""
    customer_slug = normalize_customer_slug(customer_name)
    resolved_profile: str | None = None
    resolved_role: str | None = None
    resolved_access_key: str | None = None
    resolved_secret_key: str | None = None

    if aws_auth_type == "profile":
        resolved_profile = _value_or_prompt(
            "AWS profile", aws_profile, f"{customer_slug}-root", interactive
        )
    elif aws_auth_type == "role":
        resolved_role = _value_or_prompt("AWS role ARN", aws_role, None, interactive)
    elif aws_auth_type == "user":
        resolved_access_key = _value_or_prompt(
            "AWS access key ID", aws_access_key, None, interactive
        )
        resolved_secret_key = _value_or_prompt(
            "AWS secret access key", aws_secret_key, None, interactive
        )
    else:
        raise LzaError(f"Invalid AWS auth type: {aws_auth_type}")

    config = build_workspace_config(
        customer_name=customer_name,
        customer_slug=customer_slug,
        aws_profile=resolved_profile,
        aws_role=resolved_role,
        aws_access_key=resolved_access_key,
        aws_secret_key=resolved_secret_key,
        aws_region=_value_or_prompt("AWS region", aws_region, "us-east-1", interactive),
        lza_version=_value_or_prompt("LZA version", lza_version, LzaConfig().version, interactive),
    )
    template_dir = resolve_packaged_template(config)

    validate_template(template_dir)
    validate_workspace_target(workspace_dir, force)

    if skip_aws_check:
        identity = None
    else:
        identity = validate_aws_credentials(config.aws)

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
    aws_profile: str | None = None,
    aws_role: str | None = None,
    aws_access_key: str | None = None,
    aws_secret_key: str | None = None,
    aws_region: str,
    lza_version: str,
) -> WorkspaceConfig:
    """Build init configuration; future CLI overrides belong here."""
    return WorkspaceConfig(
        customer=CustomerConfig(name=customer_name, slug=customer_slug),
        aws=AwsConfig(
            profile=aws_profile,
            role=aws_role,
            access_key=aws_access_key,
            secret_access_key=aws_secret_key,
            region=aws_region,
        ),
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
    print_dry_run_header("lza init")
    print_kv("Workspace", workspace_dir)
    print_kv("Template", config.configuration.template.name)
    console.print("Planned writes:")
    for path in planned_write_paths(workspace_dir, config):
        console.print(f"  - {path}")
    if identity:
        print_kv("AWS account", identity["account"])
        print_kv("Caller ARN", identity["arn"])


def print_success_summary(
    workspace_dir: Path,
    config: WorkspaceConfig,
    identity: dict[str, str] | None,
) -> None:
    print_success("Initialized LZA workspace")
    print_kv("Workspace", workspace_dir)
    print_kv("Customer", f"{config.customer.name} ({config.customer.slug})")
    if config.aws.profile:
        print_kv("AWS profile", config.aws.profile)
    elif config.aws.role:
        print_kv("AWS role", config.aws.role)
    elif config.aws.access_key:
        print_kv("AWS access key", config.aws.access_key)
    print_kv("AWS region", config.aws.region)
    print_kv("LZA version", config.lza.version)
    if identity:
        print_kv("AWS account", identity["account"])
        print_kv("Caller ARN", identity["arn"])


def _value_or_prompt(label: str, value: str | None, default: str | None, interactive: bool) -> str:
    if value:
        return value
    if interactive:
        if default is not None:
            return typer.prompt(label, default=default)
        return typer.prompt(label)
    if default is not None:
        return default
    raise LzaError(f"{label} is required.")
