"""Implementation for the `lza init` command."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from lza_workbench.aws.identity import validate_aws_profile
from lza_workbench.commands import DEFAULT_AWS_REGION, DEFAULT_LZA_VERSION
from lza_workbench.core.project import InitRequest
from lza_workbench.core.templates import (
    DEFAULT_TEMPLATE_SOURCE,
    resolve_template_source,
    validate_template,
)
from lza_workbench.core.workspace import (
    create_workspace,
    normalize_customer_slug,
    planned_write_paths,
    validate_project_target,
)

console = Console()


def collect_init_request(
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
) -> InitRequest:
    """Resolve CLI inputs and prompt for required missing values when possible."""
    customer_slug = normalize_customer_slug(customer_name)
    project_dir = resolve_init_project_dir(
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

    return InitRequest(
        customer_name=customer_name,
        customer_slug=customer_slug,
        workspace_dir=project_dir,
        project_dir=project_dir,
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


def resolve_init_project_dir(
    *,
    customer_name: str,
    workspace_dir: Path | None,
    interactive: bool,
) -> Path:
    """Resolve the init target before collecting template and AWS settings."""
    customer_slug = normalize_customer_slug(customer_name)
    return _workspace_dir_or_prompt(
        workspace_dir,
        default=Path.cwd() / customer_slug,
        interactive=interactive,
    ).expanduser().resolve()


def run_init(request: InitRequest) -> None:
    """Create a customer workspace from a resolved init request."""
    validate_template(request.template_config_dir)
    validate_project_target(request.project_dir, request.force)

    if not request.skip_aws_check:
        identity = validate_aws_profile(request.aws_profile, request.aws_region)
    else:
        identity = None

    if request.dry_run:
        print_dry_run_summary(request, identity)
        return

    create_workspace(request)
    validate_template(request.project_dir / "aws-accelerator-config")
    print_success_summary(request, identity)


def print_dry_run_summary(request: InitRequest, identity: dict[str, str] | None) -> None:
    console.print("[bold]Dry run: lza init[/bold]")
    console.print(f"Workspace: {request.project_dir}")
    console.print(f"Template source: {request.template_source}")
    console.print(f"Template files: {request.template_config_dir}")
    console.print("Planned writes:")
    for path in planned_write_paths(request):
        console.print(f"  - {path}")
    if identity:
        console.print(f"AWS account: {identity['account']}")
        console.print(f"Caller ARN: {identity['arn']}")


def print_success_summary(request: InitRequest, identity: dict[str, str] | None) -> None:
    console.print("[bold green]Initialized LZA project workspace[/bold green]")
    console.print(f"Workspace: {request.project_dir}")
    console.print(f"Customer: {request.customer_name} ({request.customer_slug})")
    console.print(f"AWS profile: {request.aws_profile}")
    console.print(f"AWS region: {request.aws_region}")
    console.print(f"LZA version: {request.lza_version}")
    console.print(f"Template source: {request.template_source}")
    if identity:
        console.print(f"AWS account: {identity['account']}")
        console.print(f"Caller ARN: {identity['arn']}")
    console.print("Next commands:")
    console.print(f"  cd {request.project_dir}")
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
