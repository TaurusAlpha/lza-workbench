"""Initialize a customer workspace from the default workspace configuration."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.aws.client_factory import validate_aws_credentials
from lza_workbench.core.errors import LzaError
from lza_workbench.core.templates import resolve_template_source, validate_template
from lza_workbench.utils.helpers import normalize_customer_slug, value_or_prompt
from lza_workbench.utils.output import (
    console,
    print_dry_run_header,
    print_kv,
    print_success,
)
from lza_workbench.workspace.models import (
    AwsConfig,
    ConfigurationConfig,
    CustomerConfig,
    LzaConfig,
    WorkspaceConfig,
    WorkspaceState,
)
from lza_workbench.workspace.paths import resolve_init_workspace_dir
from lza_workbench.workspace.setup import (
    create_workspace,
    overwrite_workspace_metadata,
    planned_write_paths,
    validate_workspace_structure,
)


def run_init(
    *,
    customer_name: str,
    workspace_dir: Path | None,
    aws_auth_type: str = "profile",
    aws_profile: str | None = None,
    aws_region: str | None = None,
    lza_version: str | None = None,
    dry_run: bool,
    force: bool,
    skip_aws_check: bool,
    interactive: bool,
) -> None:
    """Create a customer workspace using the configured packaged template."""
    customer_slug = normalize_customer_slug(customer_name)
    default_workspace_dir = resolve_init_workspace_dir(customer_name)
    if workspace_dir is None:
        workspace_dir = (
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
        workspace_dir = resolve_init_workspace_dir(customer_name, workspace_dir)

    existing_directory = validate_workspace_structure(workspace_dir, force)
    if existing_directory and not (workspace_dir / ConfigurationConfig().local_path).is_dir():
        raise LzaError(
            f"Cannot overwrite metadata: LZA configuration directory is missing in {workspace_dir}."
        )

    if aws_auth_type == "profile":
        resolved_profile = value_or_prompt(
            "AWS profile", aws_profile, f"{customer_slug}-root", interactive
        )
    else:
        raise LzaError(f"Invalid AWS auth type: {aws_auth_type}")

    config = build_workspace_config(
        customer_name=customer_name,
        customer_slug=customer_slug,
        aws_profile=resolved_profile,
        aws_region=value_or_prompt("AWS region", aws_region, "us-east-1", interactive),
        lza_version=value_or_prompt("LZA version", lza_version, LzaConfig().version, interactive),
    )
    template_dir = resolve_packaged_template(config)

    # TODO(refactor): Prompt for a packaged template after multiple templates exist.
    if not existing_directory:
        validate_template(template_dir)

    if skip_aws_check:
        identity = None
    else:
        identity = validate_aws_credentials(config.aws)

    if dry_run:
        print_dry_run_summary(workspace_dir, config, identity)
        return

    state = WorkspaceState.from_config(config)
    if existing_directory:
        overwrite_workspace_metadata(workspace_dir, config, state)
    else:
        create_workspace(
            workspace_dir=workspace_dir,
            template_config_dir=template_dir,
            config=config,
            state=state,
        )
        validate_template(workspace_dir / config.configuration.local_path)
    print_success_summary(workspace_dir, config, identity)


def build_workspace_config(
    *,
    customer_name: str,
    customer_slug: str,
    aws_profile: str | None = None,
    aws_region: str,
    lza_version: str,
) -> WorkspaceConfig:
    """Build init configuration; future CLI overrides belong here."""
    return WorkspaceConfig(
        customer=CustomerConfig(name=customer_name, slug=customer_slug),
        aws=AwsConfig(
            profile=aws_profile,
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
    print_kv("AWS region", config.aws.region)
    print_kv("LZA version", config.lza.version)
    if identity:
        print_kv("AWS account", identity["account"])
        print_kv("Caller ARN", identity["arn"])
