"""Initialize a customer workspace.

Collect command options, resolve defaults, and orchestrate workspace creation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import typer
from rich.console import Console

from lza_workbench.aws.identity import validate_aws_profile
from lza_workbench.commands import DEFAULT_AWS_REGION, DEFAULT_LZA_VERSION
from lza_workbench.core.templates import (
    DEFAULT_TEMPLATE_SOURCE,
    resolve_template_source,
    validate_template,
)
from lza_workbench.core.workspace import (
    WorkspaceConfig,
    WorkspaceState,
    create_workspace,
    normalize_customer_slug,
    planned_write_paths,
    validate_workspace_target,
)

console = Console()


@dataclass(frozen=True)
class InitOptions:
    """Resolved values controlling one init command invocation."""

    customer_name: str
    customer_slug: str
    workspace_dir: Path
    aws_profile: str
    aws_region: str
    lza_version: str
    template_source: str
    template_source_type: str
    template_config_dir: Path
    dry_run: bool = False
    force: bool = False
    skip_aws_check: bool = False


def collect_init_options(
    *,
    customer_name: str,
    workspace_dir: Path | None,
    aws_profile: str | None,
    aws_region: str | None,
    lza_version: str | None,
    template_source: str | None,
    dry_run: bool,
    force: bool,
    skip_aws_check: bool,
    interactive: bool,
) -> InitOptions:
    """Resolve CLI inputs and prompt for required missing values when possible."""
    customer_slug = normalize_customer_slug(customer_name)
    workspace_dir = resolve_init_workspace_dir(
        customer_name=customer_name,
        workspace_dir=workspace_dir,
        interactive=interactive,
    )
    selected_aws_profile = _string_value_or_prompt(
        "AWS profile",
        aws_profile,
        default=customer_slug,
        interactive=interactive,
    )
    selected_lza_version = _string_value_or_prompt(
        "LZA version",
        lza_version,
        default=DEFAULT_LZA_VERSION,
        interactive=interactive,
    )
    selected_aws_region = _string_value_or_prompt(
        "AWS region",
        aws_region,
        default=DEFAULT_AWS_REGION,
        interactive=interactive,
    )
    selected_template_source = _string_value_or_prompt(
        "Template source",
        template_source,
        default=DEFAULT_TEMPLATE_SOURCE,
        interactive=interactive,
    )
    resolved_template = resolve_template_source(selected_template_source)

    return InitOptions(
        customer_name=customer_name,
        customer_slug=customer_slug,
        workspace_dir=workspace_dir,
        aws_profile=selected_aws_profile,
        aws_region=selected_aws_region,
        lza_version=selected_lza_version,
        template_source=resolved_template.source,
        template_source_type=resolved_template.source_type,
        template_config_dir=resolved_template.config_dir,
        dry_run=dry_run,
        force=force,
        skip_aws_check=skip_aws_check,
    )


def resolve_init_workspace_dir(
    *,
    customer_name: str,
    workspace_dir: Path | None,
    interactive: bool,
) -> Path:
    """Resolve the workspace target before collecting template and AWS settings."""
    customer_slug = normalize_customer_slug(customer_name)
    return _workspace_dir_or_prompt(
        workspace_dir,
        default=Path.cwd() / customer_slug,
        interactive=interactive,
    ).expanduser().resolve()


def run_init(options: InitOptions) -> None:
    """Create a customer workspace from resolved init options."""
    validate_template(options.template_config_dir)
    validate_workspace_target(options.workspace_dir, options.force)
    config = build_workspace_config(options)
    state = WorkspaceState.from_config(config)

    if not options.skip_aws_check:
        identity = validate_aws_profile(options.aws_profile, options.aws_region)
    else:
        identity = None

    if options.dry_run:
        print_dry_run_summary(options, identity)
        return

    create_workspace(
        workspace_dir=options.workspace_dir,
        template_config_dir=options.template_config_dir,
        config=config,
        state=state,
    )
    validate_template(options.workspace_dir / "aws-accelerator-config")
    print_success_summary(options, identity)


def print_dry_run_summary(options: InitOptions, identity: dict[str, str] | None) -> None:
    console.print("[bold]Dry run: lza init[/bold]")
    console.print(f"Workspace: {options.workspace_dir}")
    console.print(f"Template source: {options.template_source}")
    console.print(f"Template files: {options.template_config_dir}")
    console.print("Planned writes:")
    for path in planned_write_paths(options.workspace_dir):
        console.print(f"  - {path}")
    if identity:
        console.print(f"AWS account: {identity['account']}")
        console.print(f"Caller ARN: {identity['arn']}")


def print_success_summary(options: InitOptions, identity: dict[str, str] | None) -> None:
    console.print("[bold green]Initialized LZA workspace[/bold green]")
    console.print(f"Workspace: {options.workspace_dir}")
    console.print(f"Customer: {options.customer_name} ({options.customer_slug})")
    console.print(f"AWS profile: {options.aws_profile}")
    console.print(f"AWS region: {options.aws_region}")
    console.print(f"LZA version: {options.lza_version}")
    console.print(f"Template source: {options.template_source}")
    if identity:
        console.print(f"AWS account: {identity['account']}")
        console.print(f"Caller ARN: {identity['arn']}")
    console.print("Next commands:")
    console.print(f"  cd {options.workspace_dir}")
    console.print("  lza profile check")
    console.print("  lza installer deploy --dry-run")


def _workspace_dir_or_prompt(value: Path | None, default: Path, interactive: bool) -> Path:
    if value:
        return value
    if interactive:
        return Path(typer.prompt("Workspace directory", default=str(default)))
    return default


def _string_value_or_prompt(
    label: str,
    value: str | None,
    default: str | None,
    interactive: bool,
) -> str:
    if value:
        return value

    if interactive:
        if default:
            return typer.prompt(label, default=default)
        return typer.prompt(label)

    if default:
        return default

    raise typer.BadParameter(f"{label} is required in non-interactive mode.")


def build_workspace_config(options: InitOptions) -> WorkspaceConfig:
    """Build the persisted configuration produced by init."""
    return WorkspaceConfig.create(
        customer_name=options.customer_name,
        customer_slug=options.customer_slug,
        aws_profile=options.aws_profile,
        aws_region=options.aws_region,
        lza_version=options.lza_version,
        template_source=options.template_source,
        template_source_type=options.template_source_type,
    )
