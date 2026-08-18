"""Workflow for bootstrapping LZA Workbench AWS prerequisite resources."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.aws.s3 import (
    ensure_s3_workbench_assets_bucket,
    get_workbench_assets_bucket_name,
    inspect_s3_bucket,
)
from lza_workbench.errors import LzaError
from lza_workbench.workspace.config import write_workspace_config
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context
from lza_workbench.workspace.schema import WorkspaceConfig
from lza_workbench.workspace.state import write_workspace_state


@dataclass(frozen=True)
class BootstrapPlanResult:
    """Structured plan for bootstrapping AWS resources for a workspace."""

    workspace_dir: Path
    config: WorkspaceConfig
    aws_profile: str
    aws_region: str
    account_id: str
    bucket_name: str
    bucket_exists: bool
    versioning_enabled: bool
    encryption_enabled: bool
    planned_operation: str
    actions: list[str]
    dry_run: bool


@dataclass(frozen=True)
class WorkspaceBootstrapResult:
    """Structured result of workspace bootstrap execution."""

    workspace_dir: Path
    config: WorkspaceConfig
    aws_profile: str
    aws_region: str
    account_id: str
    bucket_name: str
    planned_operation: str
    dry_run: bool
    skipped: bool
    actions_taken: list[str]


def plan_bootstrap_workflow(
    target_dir: Path | None = None,
    dry_run: bool = True,
) -> BootstrapPlanResult:
    """Inspect AWS resources and plan bootstrap actions without mutating AWS."""
    ctx = load_workspace_context(
        target_dir=target_dir,
        min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED,
    )
    workspace_dir, config = ctx.workspace_dir, ctx.config

    try:
        aws_ctx = resolve_aws_execution_context(
            profile=config.aws.profile,
            region=config.aws.region,
            role_arn=config.aws.role_arn,
            expected_account_id=config.aws.account_id,
            require_identity=True,
            require_expected_account=True,
        )
    except Exception as exc:
        raise LzaError(exc) from exc

    assert aws_ctx.identity is not None
    account_id = aws_ctx.identity["account"]
    region = aws_ctx.region
    profile = config.aws.profile or ""

    bucket_name = get_workbench_assets_bucket_name(account_id, region)
    s3_client = aws_ctx.factory.get_client("s3")

    insp = inspect_s3_bucket(client=s3_client, bucket_name=bucket_name)

    actions: list[str] = []
    if not insp["exists"]:
        planned_operation = "CREATE"
        actions.append(f"Create S3 bucket '{bucket_name}' in region '{region}'")
        actions.append(f"Enable versioning on S3 bucket '{bucket_name}'")
        actions.append(f"Enable AWS-managed KMS encryption on S3 bucket '{bucket_name}'")
    else:
        if not insp["versioning_enabled"]:
            actions.append(f"Enable versioning on S3 bucket '{bucket_name}'")
        if not insp["kms_encrypted"]:
            actions.append(f"Enable AWS-managed KMS encryption on S3 bucket '{bucket_name}'")

        if actions:
            planned_operation = "UPDATE"
        else:
            planned_operation = "NO_CHANGE"
            actions.append(f"Reuse existing S3 assets bucket '{bucket_name}' (already configured)")

    return BootstrapPlanResult(
        workspace_dir=workspace_dir,
        config=config,
        aws_profile=profile,
        aws_region=region,
        account_id=account_id,
        bucket_name=bucket_name,
        bucket_exists=insp["exists"],
        versioning_enabled=insp["versioning_enabled"],
        encryption_enabled=insp["kms_encrypted"],
        planned_operation=planned_operation,
        actions=actions,
        dry_run=dry_run,
    )


def bootstrap_workspace_workflow(
    target_dir: Path | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> WorkspaceBootstrapResult:
    """Execute workspace bootstrap workflow and return structured result."""
    del force  # Force bypasses CLI confirmation; workflow itself is idempotent
    plan = plan_bootstrap_workflow(target_dir=target_dir, dry_run=dry_run)

    if dry_run:
        return WorkspaceBootstrapResult(
            workspace_dir=plan.workspace_dir,
            config=plan.config,
            aws_profile=plan.aws_profile,
            aws_region=plan.aws_region,
            account_id=plan.account_id,
            bucket_name=plan.bucket_name,
            planned_operation=plan.planned_operation,
            dry_run=True,
            skipped=False,
            actions_taken=[],
        )

    ctx = load_workspace_context(
        target_dir=target_dir,
        min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED,
    )
    workspace_dir, config, state = ctx.workspace_dir, ctx.config, ctx.state

    aws_ctx = resolve_aws_execution_context(
        profile=config.aws.profile,
        region=config.aws.region,
        role_arn=config.aws.role_arn,
        expected_account_id=config.aws.account_id,
        require_identity=True,
        require_expected_account=True,
    )
    s3_client = aws_ctx.factory.get_client("s3")

    actions_taken = ensure_s3_workbench_assets_bucket(
        client=s3_client,
        bucket_name=plan.bucket_name,
        region=plan.aws_region,
    )

    # Persist assets bucket to lza-workspace.yaml
    config.assets_bucket = plan.bucket_name
    write_workspace_config(workspace_dir, config)

    # Persist assets bucket and bootstrap timestamp to .lza/state.json
    state.assets_bucket_name = plan.bucket_name
    state.bootstrapped_at = datetime.now(UTC)
    state.management_account_id = plan.account_id
    write_workspace_state(workspace_dir, state)

    return WorkspaceBootstrapResult(
        workspace_dir=workspace_dir,
        config=config,
        aws_profile=plan.aws_profile,
        aws_region=plan.aws_region,
        account_id=plan.account_id,
        bucket_name=plan.bucket_name,
        planned_operation=plan.planned_operation,
        dry_run=False,
        skipped=False,
        actions_taken=actions_taken,
    )


__all__ = [
    "BootstrapPlanResult",
    "WorkspaceBootstrapResult",
    "bootstrap_workspace_workflow",
    "plan_bootstrap_workflow",
]
