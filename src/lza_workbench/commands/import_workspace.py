"""Adopt an existing LZA configuration as a workbench workspace."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import typer
from rich.console import Console

from lza_workbench.aws.identity import validate_aws_profile
from lza_workbench.commands.init_workspace import resolve_init_workspace_dir
from lza_workbench.core.templates import validate_template
from lza_workbench.core.workspace import (
    AwsConfig,
    ConfigurationConfig,
    ConfigurationTemplateConfig,
    CustomerConfig,
    LzaConfig,
    WorkspaceConfig,
    WorkspaceState,
    load_workspace_config,
    load_workspace_state,
    normalize_customer_slug,
    write_workspace_config,
    write_workspace_state,
)

console = Console()


@dataclass(frozen=True)
class ExistingMetadata:
    """Existing generated metadata, if the workspace has been imported before."""

    config: WorkspaceConfig
    state: WorkspaceState


def run_import(
    *,
    customer_name: str,
    workspace_dir: Path | None,
    config_dir: Path | None,
    aws_profile: str | None,
    aws_region: str | None,
    lza_version: str | None,
    dry_run: bool,
    force: bool,
    skip_aws_check: bool,
    interactive: bool,
) -> None:
    """Create or update generated metadata without changing LZA configuration files."""
    workspace_dir, config_dir = resolve_import_paths(
        customer_name=customer_name,
        workspace_dir=workspace_dir,
        config_dir=config_dir,
        interactive=interactive,
    )
    validate_template(config_dir)
    existing = load_existing_metadata(workspace_dir)
    customer_slug = _customer_slug(customer_name, existing)
    config = build_workspace_config(
        customer_name=customer_name,
        customer_slug=customer_slug,
        aws_profile=_value_or_prompt(
            "AWS profile", aws_profile, existing.config.aws.profile if existing else customer_slug, interactive
        ),
        aws_region=_value_or_prompt(
            "AWS region", aws_region, existing.config.aws.region if existing else AwsConfig().region, interactive
        ),
        lza_version=_value_or_prompt(
            "LZA version", lza_version, existing.config.lza.version if existing else LzaConfig().version, interactive
        ),
        workspace_dir=workspace_dir,
        config_dir=config_dir,
        existing_config=existing.config if existing else None,
    )
    state = existing.state if existing else WorkspaceState.from_config(config)

    identity = None if skip_aws_check else validate_aws_profile(config.aws.profile or "", config.aws.region)
    paths = _metadata_paths(workspace_dir, existing, config, state)
    if dry_run:
        _print_summary("Dry run: lza import", workspace_dir, config_dir, paths, identity)
        return
    if not paths:
        console.print("[bold green]Workspace already imported; no metadata changes[/bold green]")
        return

    (workspace_dir / ".lza").mkdir(parents=True, exist_ok=True)
    if workspace_dir / "lza-workspace.yaml" in paths:
        write_workspace_config(workspace_dir / "lza-workspace.yaml", config)
    if workspace_dir / ".lza" / "state.json" in paths:
        write_workspace_state(workspace_dir / ".lza" / "state.json", state)
    _print_summary("Imported LZA workspace", workspace_dir, config_dir, paths, identity)


def resolve_import_paths(
    *,
    customer_name: str,
    workspace_dir: Path | None,
    config_dir: Path | None,
    interactive: bool,
) -> tuple[Path, Path]:
    """Resolve the workspace and its existing LZA configuration directory."""
    if config_dir is not None:
        resolved_config_dir = config_dir.expanduser().resolve()
        resolved_workspace_dir = workspace_dir.expanduser().resolve() if workspace_dir else resolved_config_dir.parent
    else:
        resolved_workspace_dir = resolve_init_workspace_dir(
            customer_name=customer_name,
            workspace_dir=workspace_dir,
            interactive=interactive,
        )
        resolved_config_dir = resolved_workspace_dir / ConfigurationConfig().local_path

    if not resolved_workspace_dir.is_dir():
        raise typer.BadParameter(f"Workspace directory does not exist: {resolved_workspace_dir}")
    if not resolved_config_dir.is_dir():
        raise typer.BadParameter(f"Configuration directory does not exist: {resolved_config_dir}")
    if resolved_config_dir.is_symlink():
        raise typer.BadParameter(f"Configuration directory must not be a symlink: {resolved_config_dir}")
    try:
        resolved_config_dir.relative_to(resolved_workspace_dir)
    except ValueError as exc:
        raise typer.BadParameter("Configuration directory must be inside the workspace.") from exc
    return resolved_workspace_dir, resolved_config_dir


def load_existing_metadata(workspace_dir: Path) -> ExistingMetadata | None:
    """Load a complete existing metadata pair, if present."""
    config_path = workspace_dir / "lza-workspace.yaml"
    state_path = workspace_dir / ".lza" / "state.json"
    if config_path.exists() != state_path.exists():
        raise typer.BadParameter("Workspace has partial metadata; both metadata files are required.")
    if not config_path.exists():
        return None
    try:
        return ExistingMetadata(load_workspace_config(config_path), load_workspace_state(state_path))
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


def build_workspace_config(
    *,
    customer_name: str,
    customer_slug: str,
    aws_profile: str,
    aws_region: str,
    lza_version: str,
    workspace_dir: Path,
    config_dir: Path,
    existing_config: WorkspaceConfig | None,
) -> WorkspaceConfig:
    """Build import metadata; future CLI overrides belong here."""
    configuration = ConfigurationConfig(
        local_path=str(config_dir.relative_to(workspace_dir)),
        template=ConfigurationTemplateConfig(source="local", path=str(config_dir)),
    )
    fields = {
        "customer": CustomerConfig(name=customer_name, slug=customer_slug),
        "aws": AwsConfig(profile=aws_profile, region=aws_region),
        "lza": LzaConfig(version=lza_version),
        "configuration": configuration,
    }
    if existing_config is not None:
        return existing_config.model_copy(update=fields)
    return WorkspaceConfig(**fields)


def _metadata_paths(
    workspace_dir: Path,
    existing: ExistingMetadata | None,
    config: WorkspaceConfig,
    state: WorkspaceState,
) -> list[Path]:
    config_path = workspace_dir / "lza-workspace.yaml"
    state_path = workspace_dir / ".lza" / "state.json"
    if existing is None:
        return [config_path, state_path]
    return [
        path
        for path, changed in ((config_path, existing.config != config), (state_path, existing.state != state))
        if changed
    ]


def _customer_slug(customer_name: str, existing: ExistingMetadata | None) -> str:
    if existing and existing.config.customer.name == customer_name:
        return existing.config.customer.slug
    return normalize_customer_slug(customer_name)


def _print_summary(
    title: str,
    workspace_dir: Path,
    config_dir: Path,
    paths: list[Path],
    identity: dict[str, str] | None,
) -> None:
    console.print(f"[bold green]{title}[/bold green]")
    console.print(f"Workspace: {workspace_dir}")
    console.print(f"Configuration: {config_dir}")
    console.print("Affected paths:")
    for path in paths:
        console.print(f"  - {path}")
    if identity:
        console.print(f"AWS account: {identity['account']}")
        console.print(f"Caller ARN: {identity['arn']}")
    console.print("Customer configuration files were preserved.")


def _value_or_prompt(label: str, value: str | None, default: str | None, interactive: bool) -> str:
    if value:
        return value
    if default:
        return typer.prompt(label, default=default) if interactive else default
    raise typer.BadParameter(f"{label} is required.")
