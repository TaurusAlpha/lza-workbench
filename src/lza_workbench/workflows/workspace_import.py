"""Workflow for importing and adopting an existing LZA workspace."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.config.schema import ConfigurationConfig, ConfigurationTemplateConfig
from lza_workbench.config.templates import validate_template
from lza_workbench.errors import LzaError
from lza_workbench.workspace.config import (
    WORKSPACE_CONFIG_FILE,
    load_workspace_config,
    write_workspace_config,
)
from lza_workbench.workspace.paths import normalize_customer_slug
from lza_workbench.workspace.schema import (
    AwsConfig,
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


@dataclass(frozen=True)
class WorkspaceImportResult:
    """Structured result of workspace import workflow."""

    workspace_dir: Path
    config_dir: Path
    config: WorkspaceConfig
    state: WorkspaceState
    affected_paths: list[Path]
    identity: dict[str, str] | None
    already_imported: bool
    dry_run: bool


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


def build_import_workspace_config(
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
    """Build import metadata."""
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


def import_workspace_workflow(
    *,
    workspace_dir: Path,
    config_dir: Path | None = None,
    customer_name: str | None = None,
    aws_auth_type: str = "profile",
    aws_profile: str | None = None,
    aws_region: str = "us-east-1",
    lza_version: str = "v1.15.5",
    dry_run: bool = False,
    force: bool = False,
    skip_aws_check: bool = False,
) -> WorkspaceImportResult:
    """Execute the pure workspace import workflow and return structured result."""
    resolved_workspace_dir, resolved_config_dir = resolve_import_paths(
        workspace_dir=workspace_dir,
        config_dir=config_dir,
    )
    existing = load_existing_metadata(resolved_workspace_dir, force=force)
    validate_template(resolved_config_dir)

    if customer_name:
        resolved_customer_name = customer_name
    elif existing:
        resolved_customer_name = existing.config.customer.name
    else:
        resolved_customer_name = resolved_workspace_dir.name

    customer_slug = (
        existing.config.customer.slug
        if existing and existing.config.customer.name == resolved_customer_name
        else normalize_customer_slug(resolved_customer_name)
    )

    if aws_auth_type != "profile":
        raise LzaError(f"Invalid AWS auth type: {aws_auth_type}")

    if aws_profile:
        resolved_profile = aws_profile
    elif existing:
        resolved_profile = existing.config.aws.profile
    else:
        resolved_profile = f"{customer_slug}-root"

    if aws_region is not None:
        resolved_region = aws_region
    elif existing:
        resolved_region = existing.config.aws.region
    else:
        resolved_region = "us-east-1"

    if lza_version is not None:
        resolved_version = lza_version
    elif existing:
        resolved_version = existing.config.lza.version
    else:
        resolved_version = "v1.15.5"

    config = build_import_workspace_config(
        customer_name=resolved_customer_name,
        customer_slug=customer_slug,
        aws_profile=resolved_profile,
        aws_region=resolved_region,
        lza_version=resolved_version,
        workspace_dir=resolved_workspace_dir,
        config_dir=resolved_config_dir,
        existing_config=existing.config if existing else None,
    )
    state = existing.state if existing else WorkspaceState.from_config(config)

    identity = (
        None
        if skip_aws_check
        else resolve_aws_execution_context(
            profile=config.aws.profile,
            region=config.aws.region,
            role_arn=config.aws.role_arn,
            expected_account_id=config.aws.account_id,
            require_identity=True,
        ).identity
    )
    paths = _metadata_paths(resolved_workspace_dir, existing, config, state)

    if dry_run:
        return WorkspaceImportResult(
            workspace_dir=resolved_workspace_dir,
            config_dir=resolved_config_dir,
            config=config,
            state=state,
            affected_paths=paths,
            identity=identity,
            already_imported=not bool(paths),
            dry_run=True,
        )

    if not paths:
        return WorkspaceImportResult(
            workspace_dir=resolved_workspace_dir,
            config_dir=resolved_config_dir,
            config=config,
            state=state,
            affected_paths=[],
            identity=identity,
            already_imported=True,
            dry_run=False,
        )

    (resolved_workspace_dir / ".lza").mkdir(parents=True, exist_ok=True)
    if resolved_workspace_dir / "lza-workspace.yaml" in paths:
        write_workspace_config(resolved_workspace_dir, config)
    if resolved_workspace_dir / ".lza" / "state.json" in paths:
        write_workspace_state(resolved_workspace_dir, state)

    return WorkspaceImportResult(
        workspace_dir=resolved_workspace_dir,
        config_dir=resolved_config_dir,
        config=config,
        state=state,
        affected_paths=paths,
        identity=identity,
        already_imported=False,
        dry_run=False,
    )
