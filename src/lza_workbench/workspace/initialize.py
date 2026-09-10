"""Workspace initialization workflow and filesystem scaffolding."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from lza_workbench.errors import LzaError
from lza_workbench.infrastructure.aws.session import resolve_aws_execution_context
from lza_workbench.installer.versions import normalize_lza_version
from lza_workbench.workspace.paths import (
    normalize_customer_slug,
    normalize_path,
    resolve_init_workspace_dir,
)
from lza_workbench.workspace.persistence import (
    WORKSPACE_CONFIG_FILE,
    WORKSPACE_STATE_FILE,
    write_workspace_config,
    write_workspace_state,
)
from lza_workbench.workspace.schema import (
    WorkspaceConfig,
    WorkspaceState,
)

WORKSPACE_MANAGED_PATHS = [
    Path(".lza"),
    Path("aws-accelerator-config"),
    Path("aws-accelerator-installer"),
    WORKSPACE_CONFIG_FILE,
    WORKSPACE_STATE_FILE,
]


def validate_workspace_structure(
    workspace_dir: Path,
    force: bool = False,
) -> bool:
    """Validate an init target and return whether it already exists."""
    target = normalize_path(workspace_dir)
    if not target.exists():
        return False
    if not target.is_dir():
        raise LzaError(f"Target path exists and is not a directory: {target}")
    existing: list[Path] = []
    if not force:
        for path in WORKSPACE_MANAGED_PATHS:
            if (target / path).exists():
                existing.append(target / path)
                raise LzaError(
                    f"Found existing workspace-managed paths: {existing}. "
                    f"To adopt existing workspace, run `lza import {target}` "
                    "or use --force flag to overwrite."
                )
    return True


def create_workspace(
    *,
    workspace_dir: Path,
    config: WorkspaceConfig,
    state: WorkspaceState,
) -> None:
    """Create or reinitialize generated workspace files."""
    target = normalize_path(workspace_dir)
    target.mkdir(parents=True, exist_ok=True)
    (target / ".lza" / "logs").mkdir(parents=True, exist_ok=True)
    (target / config.installer.local_path).mkdir(parents=True, exist_ok=True)

    write_workspace_config(target, config)
    write_workspace_state(target, state)


def overwrite_workspace_metadata(
    workspace_dir: Path, config: WorkspaceConfig, state: WorkspaceState
) -> None:
    """Replace generated metadata without changing customer-owned configuration files."""
    target = normalize_path(workspace_dir)
    write_workspace_config(target, config)
    write_workspace_state(target, state)


def planned_write_paths(workspace_dir: Path, config: WorkspaceConfig) -> list[Path]:
    """Return the paths workspace initialization will create or replace."""
    return [
        workspace_dir,
        workspace_dir / WORKSPACE_CONFIG_FILE,
        workspace_dir / config.installer.local_path,
        workspace_dir / WORKSPACE_STATE_FILE,
        workspace_dir / ".lza" / "logs",
    ]


@dataclass(frozen=True)
class WorkspaceInitResult:
    """Structured result of workspace initialization workflow."""

    workspace_dir: Path
    config: WorkspaceConfig
    state: WorkspaceState
    planned_paths: list[Path]
    existing_directory: bool
    identity: dict[str, str] | None
    dry_run: bool


def init_workspace(
    *,
    customer_name: str,
    workspace_dir: Path | None = None,
    aws_auth_type: str = "profile",
    aws_profile: str | None = None,
    aws_role_arn: str | None = None,
    aws_region: str = "us-east-1",
    lza_version: str = "v1.15.5",
    dry_run: bool = False,
    force: bool = False,
    skip_aws_check: bool = True,
) -> WorkspaceInitResult:
    """Execute the pure workspace initialization workflow and return structured result."""
    customer_slug = normalize_customer_slug(customer_name)
    resolved_workspace_dir = resolve_init_workspace_dir(customer_slug, workspace_dir)

    existing_directory = validate_workspace_structure(resolved_workspace_dir, force)

    if aws_auth_type not in ("profile", "role_arn"):
        raise LzaError(f"Invalid AWS auth type: {aws_auth_type}")

    if aws_auth_type == "role_arn":
        if not aws_role_arn or not aws_role_arn.strip():
            raise LzaError("AWS auth type 'role_arn' requires --aws-role-arn / aws_role_arn.")
        resolved_profile = (aws_profile or "").strip() or None
        resolved_role_arn = aws_role_arn.strip()
    else:
        resolved_profile = aws_profile or f"{customer_slug}-root"
        resolved_role_arn = (aws_role_arn or "").strip() or None

    try:
        config = WorkspaceConfig.create(
            customer_name=customer_name,
            customer_slug=customer_slug,
            aws_profile=resolved_profile,
            aws_role_arn=resolved_role_arn,
            aws_region=aws_region,
            lza_version=normalize_lza_version(lza_version),
        )
    except ValidationError as exc:
        raise LzaError(f"Failed to initialize workspace config: {exc}") from exc

    if skip_aws_check:
        identity = None
    else:
        identity = resolve_aws_execution_context(
            profile=config.aws.profile,
            region=config.aws.region,
            role_arn=config.aws.role_arn,
            expected_account_id=config.aws.account_id,
            require_identity=True,
            prime_credentials=config.aws.prime_credentials,
        ).identity

    state = WorkspaceState.from_config(config)
    state.initialized_at = datetime.datetime.now(datetime.UTC)
    planned_paths = planned_write_paths(resolved_workspace_dir, config)

    if dry_run:
        return WorkspaceInitResult(
            workspace_dir=resolved_workspace_dir,
            config=config,
            state=state,
            planned_paths=planned_paths,
            existing_directory=existing_directory,
            identity=identity,
            dry_run=True,
        )

    if existing_directory:
        overwrite_workspace_metadata(resolved_workspace_dir, config, state)
    else:
        create_workspace(
            workspace_dir=resolved_workspace_dir,
            config=config,
            state=state,
        )

    return WorkspaceInitResult(
        workspace_dir=resolved_workspace_dir,
        config=config,
        state=state,
        planned_paths=planned_paths,
        existing_directory=existing_directory,
        identity=identity,
        dry_run=False,
    )


__all__ = [
    "WORKSPACE_MANAGED_PATHS",
    "WorkspaceInitResult",
    "create_workspace",
    "init_workspace",
    "overwrite_workspace_metadata",
    "planned_write_paths",
    "validate_workspace_structure",
]
