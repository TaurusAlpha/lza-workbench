"""Workflow for initializing a customer workspace."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.errors import LzaError
from lza_workbench.workspace.paths import normalize_customer_slug, resolve_init_workspace_dir
from lza_workbench.workspace.schema import (
    AwsConfig,
    CustomerConfig,
    LzaConfig,
    WorkspaceConfig,
    WorkspaceState,
)
from lza_workbench.workspace.setup import (
    create_workspace,
    overwrite_workspace_metadata,
    planned_write_paths,
    validate_workspace_structure,
)


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


def build_workspace_config(
    *,
    customer_name: str,
    customer_slug: str,
    aws_profile: str | None = None,
    aws_region: str = "us-east-1",
    lza_version: str = "v1.15.5",
) -> WorkspaceConfig:
    """Build init configuration model."""
    return WorkspaceConfig(
        customer=CustomerConfig(name=customer_name, slug=customer_slug),
        aws=AwsConfig(
            profile=aws_profile,
            region=aws_region,
        ),
        lza=LzaConfig(version=lza_version),
    )


def init_workspace_workflow(
    *,
    customer_name: str,
    workspace_dir: Path | None = None,
    aws_auth_type: str = "profile",
    aws_profile: str | None = None,
    aws_region: str = "us-east-1",
    lza_version: str = "v1.15.5",
    dry_run: bool = False,
    force: bool = False,
    skip_aws_check: bool = True,
) -> WorkspaceInitResult:
    """Execute the pure workspace initialization workflow and return structured result."""
    customer_slug = normalize_customer_slug(customer_name)
    resolved_workspace_dir = resolve_init_workspace_dir(customer_name, workspace_dir)

    existing_directory = validate_workspace_structure(resolved_workspace_dir, force)

    if aws_auth_type != "profile":
        raise LzaError(f"Invalid AWS auth type: {aws_auth_type}")

    resolved_profile = aws_profile or f"{customer_slug}-root"

    config = build_workspace_config(
        customer_name=customer_name,
        customer_slug=customer_slug,
        aws_profile=resolved_profile,
        aws_region=aws_region,
        lza_version=lza_version,
    )

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
