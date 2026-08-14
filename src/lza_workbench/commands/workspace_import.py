"""Adopt an existing LZA configuration as a workbench workspace."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.core.errors import LzaError
from lza_workbench.core.templates import validate_template
from lza_workbench.utils.helpers import normalize_customer_slug, value_or_prompt
from lza_workbench.utils.output import (
    console,
    print_dry_run_header,
    print_kv,
    print_success,
)
from lza_workbench.workspace.config import (
    WORKSPACE_CONFIG_FILE,
    load_workspace_config,
    write_workspace_config,
)
from lza_workbench.workspace.models import (
    AwsConfig,
    ConfigurationConfig,
    ConfigurationTemplateConfig,
    CustomerConfig,
    LzaConfig,
    WorkspaceConfig,
    WorkspaceState,
)
from lza_workbench.workspace.state import (
    WORKSPACE_STATE_FILE,
    load_workspace_state,
    write_workspace_state,
)


@dataclass(frozen=True)
class ExistingMetadata:
    """Existing generated metadata, if the workspace has been imported before."""

    config: WorkspaceConfig
    state: WorkspaceState


def run_import(
    *,
    customer_name: str | None,
    workspace_dir: Path,
    config_dir: Path | None,
    aws_auth_type: str = "profile",
    aws_profile: str | None = None,
    aws_region: str | None,
    lza_version: str | None,
    dry_run: bool,
    force: bool,
    skip_aws_check: bool,
    interactive: bool,
) -> None:
    """Create or update generated metadata without changing LZA configuration files."""
    workspace_dir, config_dir = resolve_import_paths(
        workspace_dir=workspace_dir,
        config_dir=config_dir,
    )
    existing = load_existing_metadata(workspace_dir, force=force)
    validate_template(config_dir)

    customer_name = value_or_prompt(
        "Customer name",
        customer_name,
        existing.config.customer.name if existing else workspace_dir.name,
        interactive,
    )
    customer_slug = (
        existing.config.customer.slug
        if existing and existing.config.customer.name == customer_name
        else normalize_customer_slug(customer_name)
    )
    if aws_auth_type == "profile":
        resolved_profile = value_or_prompt(
            "AWS profile",
            aws_profile,
            existing.config.aws.profile if existing else f"{customer_slug}-root",
            interactive,
        )
    else:
        raise LzaError(f"Invalid AWS auth type: {aws_auth_type}")

    config = build_workspace_config(
        customer_name=customer_name,
        customer_slug=customer_slug,
        aws_profile=resolved_profile,
        aws_region=value_or_prompt(
            "AWS region",
            aws_region,
            existing.config.aws.region if existing else "us-east-1",
            interactive,
        ),
        lza_version=value_or_prompt(
            "LZA version",
            lza_version,
            existing.config.lza.version if existing else LzaConfig().version,
            interactive,
        ),
        workspace_dir=workspace_dir,
        config_dir=config_dir,
        existing_config=existing.config if existing else None,
    )
    state = existing.state if existing else WorkspaceState.from_config(config)

    identity = (
        None
        if skip_aws_check
        else resolve_aws_execution_context(config.aws, require_identity=True).identity
    )
    paths = _metadata_paths(workspace_dir, existing, config, state)
    if dry_run:
        _print_summary("Dry run: lza import", workspace_dir, config_dir, paths, identity)
        return
    if not paths:
        print_success("Workspace already imported; no metadata changes")
        return

    (workspace_dir / ".lza").mkdir(parents=True, exist_ok=True)
    if workspace_dir / "lza-workspace.yaml" in paths:
        write_workspace_config(workspace_dir, config)
    if workspace_dir / ".lza" / "state.json" in paths:
        write_workspace_state(workspace_dir, state)
    _print_summary("Imported LZA workspace", workspace_dir, config_dir, paths, identity)


def resolve_import_paths(*, workspace_dir: Path, config_dir: Path | None) -> tuple[Path, Path]:
    """Resolve the workspace and its existing LZA configuration directory."""
    if config_dir is not None:
        resolved_config_dir = config_dir.expanduser().resolve()
        resolved_workspace_dir = workspace_dir.expanduser().resolve()
    else:
        resolved_workspace_dir = workspace_dir.expanduser().resolve()
        resolved_config_dir = resolved_workspace_dir / ConfigurationConfig().local_path

    if not resolved_workspace_dir.is_dir():
        raise LzaError(f"Workspace directory does not exist: {resolved_workspace_dir}")
    if not resolved_config_dir.is_dir():
        raise LzaError(f"Configuration directory does not exist: {resolved_config_dir}")
    if resolved_config_dir.is_symlink():
        raise LzaError(f"Configuration directory must not be a symlink: {resolved_config_dir}")
    try:
        resolved_config_dir.relative_to(resolved_workspace_dir)
    except ValueError as exc:
        raise LzaError("Configuration directory must be inside the workspace.") from exc
    return resolved_workspace_dir, resolved_config_dir


def load_existing_metadata(workspace_dir: Path, *, force: bool) -> ExistingMetadata | None:
    """Load a complete existing metadata pair, if present."""
    config_path = workspace_dir / WORKSPACE_CONFIG_FILE
    state_path = workspace_dir / WORKSPACE_STATE_FILE
    try:
        if config_path.exists() != state_path.exists():
            raise ValueError("Workspace has partial metadata; both metadata files are required.")
        if not config_path.exists():
            return None
        return ExistingMetadata(
            config=load_workspace_config(workspace_dir),
            state=load_workspace_state(workspace_dir),
        )
    except ValueError as exc:
        if force:
            return None
        raise LzaError(
            f"Invalid workspace metadata in {workspace_dir}: {exc}. "
            f"Run `lza import {workspace_dir} --force` to replace it."
        ) from exc


def build_workspace_config(
    *,
    customer_name: str,
    customer_slug: str,
    aws_profile: str | None = None,
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
        "aws": AwsConfig(
            profile=aws_profile,
            region=aws_region,
        ),
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
    config_path = workspace_dir / WORKSPACE_CONFIG_FILE
    state_path = workspace_dir / WORKSPACE_STATE_FILE
    if existing is None:
        return [config_path, state_path]
    return [
        path
        for path, changed in (
            (config_path, existing.config != config),
            (state_path, existing.state != state),
        )
        if changed
    ]


def _print_summary(
    title: str,
    workspace_dir: Path,
    config_dir: Path,
    paths: list[Path],
    identity: dict[str, str] | None,
) -> None:
    if title.startswith("Dry run:"):
        command_name = title.split(":", 1)[1].strip()
        print_dry_run_header(command_name)
    else:
        print_success(title)
    print_kv("Workspace", workspace_dir)
    print_kv("Configuration", config_dir)
    console.print("Affected paths:")
    for path in paths:
        console.print(f"  - {path}")
    if identity:
        print_kv("AWS account", identity["account"])
        print_kv("Caller ARN", identity["arn"])
    console.print("Customer configuration files were preserved.")
