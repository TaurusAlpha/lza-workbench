"""Workflow for bootstrapping LZA Workbench AWS prerequisite resources."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lza_workbench.aws.codecommit import (
    ensure_codecommit_repository,
    inspect_codecommit_config_repository,
)
from lza_workbench.aws.context import AwsExecutionContext, resolve_aws_execution_context
from lza_workbench.aws.s3 import (
    create_s3_bucket,
    inspect_s3_bucket,
    put_s3_bucket_encryption,
    put_s3_bucket_versioning,
)
from lza_workbench.errors import LzaError
from lza_workbench.workspace.config import write_workspace_config
from lza_workbench.workspace.context import (
    WorkspaceContext,
    WorkspaceReadinessLevel,
    load_workspace_context,
)
from lza_workbench.workspace.schema import WorkspaceConfig
from lza_workbench.workspace.state import load_workspace_state, write_workspace_state


def get_workbench_assets_bucket_name(account_id: str, region: str) -> str:
    """Derive standard LZA Workbench assets bucket name."""
    clean_account = account_id.strip()
    clean_region = region.strip()
    return f"s3-lza-workbench-assets-{clean_account}-{clean_region}"


def ensure_s3_workbench_assets_bucket(
    *,
    client: Any,
    bucket_name: str,
    region: str,
) -> list[str]:
    """Ensure the Workbench assets bucket exists, is versioned, and KMS encrypted."""
    actions_taken: list[str] = []
    insp = inspect_s3_bucket(client=client, bucket_name=bucket_name)

    if not insp["exists"]:
        create_s3_bucket(client=client, bucket_name=bucket_name, region=region)
        actions_taken.append(f"Created S3 bucket '{bucket_name}' in region '{region}'")

    if not insp["versioning_enabled"]:
        put_s3_bucket_versioning(client=client, bucket_name=bucket_name, enabled=True)
        actions_taken.append(f"Enabled versioning on S3 bucket '{bucket_name}'")

    if not insp["kms_encrypted"]:
        put_s3_bucket_encryption(client=client, bucket_name=bucket_name)
        actions_taken.append(f"Enabled AWS-managed KMS encryption on S3 bucket '{bucket_name}'")

    if not actions_taken:
        actions_taken.append(f"Reused existing S3 assets bucket '{bucket_name}'")

    return actions_taken


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
    bucket_planned_operation: str
    codecommit_repo_name: str | None
    codecommit_branch_name: str | None
    codecommit_repo_exists: bool
    codecommit_branch_exists: bool
    codecommit_repo_planned_operation: str
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
    codecommit_repo_name: str | None
    codecommit_branch_name: str | None
    codecommit_repo_planned_operation: str
    planned_operation: str
    dry_run: bool
    skipped: bool
    actions_taken: list[str]


@dataclass(frozen=True)
class BootstrapPreparation:
    """Resolved workspace, AWS context, and plan for one bootstrap execution."""

    context: WorkspaceContext
    aws_context: AwsExecutionContext
    plan: BootstrapPlanResult


def _resolve_bootstrap_aws_context(config: WorkspaceConfig) -> AwsExecutionContext:
    """Resolve the authenticated AWS target required for bootstrap operations."""
    try:
        return resolve_aws_execution_context(
            profile=config.aws.profile,
            region=config.aws.region,
            role_arn=config.aws.role_arn,
            expected_account_id=config.aws.account_id,
            require_identity=True,
            require_expected_account=True,
        )
    except LzaError:
        raise
    except Exception as exc:
        raise LzaError(f"AWS identity resolution failed: {exc}") from exc


def _build_bootstrap_plan(
    *,
    workspace_dir: Path,
    config: WorkspaceConfig,
    imported: bool,
    aws_context: AwsExecutionContext,
    dry_run: bool,
) -> BootstrapPlanResult:
    """Inspect bootstrap resources using one resolved workspace and AWS context."""
    aws_ctx = aws_context
    assert aws_ctx.identity is not None
    account_id = aws_ctx.identity["account"]
    region = aws_ctx.region
    profile = config.aws.profile or ""

    bucket_name = get_workbench_assets_bucket_name(account_id, region)
    s3_client = aws_ctx.factory.get_client("s3")

    insp = inspect_s3_bucket(client=s3_client, bucket_name=bucket_name)

    actions: list[str] = []
    if not insp["exists"]:
        bucket_planned_operation = "CREATE"
        actions.append(f"Create S3 bucket '{bucket_name}' in region '{region}'")
        actions.append(f"Enable versioning on S3 bucket '{bucket_name}'")
        actions.append(f"Enable AWS-managed KMS encryption on S3 bucket '{bucket_name}'")
    else:
        if not insp["versioning_enabled"]:
            actions.append(f"Enable versioning on S3 bucket '{bucket_name}'")
        if not insp["kms_encrypted"]:
            actions.append(f"Enable AWS-managed KMS encryption on S3 bucket '{bucket_name}'")

        if actions:
            bucket_planned_operation = "UPDATE"
        else:
            bucket_planned_operation = "NO_CHANGE"
            actions.append(f"Reuse existing S3 assets bucket '{bucket_name}' (already configured)")

    is_codecommit_config = config.configuration.repository.type == "codecommit"

    cc_repo_name: str | None = None
    cc_branch_name: str | None = None
    cc_repo_exists = False
    cc_branch_exists = False
    cc_planned_op = "N/A"

    if is_codecommit_config:
        cc_repo_name = config.configuration.repository.repository_name or "lza-config-source"
        cc_branch_name = config.configuration.repository.branch or "main"
        cc_client = aws_ctx.factory.get_client("codecommit")
        cc_insp = inspect_codecommit_config_repository(
            client=cc_client,
            repository_name=cc_repo_name,
            branch_name=cc_branch_name,
        )
        cc_repo_exists = cc_insp["exists"]
        cc_branch_exists = cc_insp["branch_exists"]

        if not cc_insp["accessible"] and not cc_insp["not_found"]:
            raise LzaError(
                f"Unable to access configured CodeCommit repository '{cc_repo_name}': "
                f"{cc_insp['error'] or 'unknown error'}"
            )

        if imported:
            if cc_repo_exists:
                cc_planned_op = "NO_CHANGE"
                actions.append(
                    f"Validate existing CodeCommit repository '{cc_repo_name}' "
                    f"branch '{cc_branch_name}' (imported)"
                )
            else:
                cc_planned_op = "MISSING"
                actions.append(
                    f"[bold red]MISSING[/bold red] CodeCommit repository '{cc_repo_name}' "
                    "not found (imported resources must not be recreated automatically)"
                )
        elif cc_repo_exists:
            cc_planned_op = "NO_CHANGE"
            actions.append(f"Reuse existing CodeCommit repository '{cc_repo_name}'")
        else:
            cc_planned_op = "CREATE"
            actions.append(f"Create CodeCommit repository '{cc_repo_name}' in region '{region}'")

    if cc_planned_op == "MISSING":
        overall_planned_operation = "MISSING"
    elif bucket_planned_operation == "CREATE" or cc_planned_op == "CREATE":
        overall_planned_operation = "CREATE"
    elif bucket_planned_operation == "UPDATE" or cc_planned_op == "UPDATE":
        overall_planned_operation = "UPDATE"
    else:
        overall_planned_operation = "NO_CHANGE"

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
        bucket_planned_operation=bucket_planned_operation,
        codecommit_repo_name=cc_repo_name,
        codecommit_branch_name=cc_branch_name,
        codecommit_repo_exists=cc_repo_exists,
        codecommit_branch_exists=cc_branch_exists,
        codecommit_repo_planned_operation=cc_planned_op,
        planned_operation=overall_planned_operation,
        actions=actions,
        dry_run=dry_run,
    )


def prepare_bootstrap_workflow(
    target_dir: Path | None = None,
    dry_run: bool = False,
) -> BootstrapPreparation:
    """Resolve one workspace and AWS target for bootstrap planning and execution."""
    context = load_workspace_context(
        target_dir=target_dir,
        min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED,
    )
    aws_context = _resolve_bootstrap_aws_context(context.config)
    plan = _build_bootstrap_plan(
        workspace_dir=context.workspace_dir,
        config=context.config,
        imported=context.state.imported is True,
        aws_context=aws_context,
        dry_run=dry_run,
    )
    return BootstrapPreparation(context=context, aws_context=aws_context, plan=plan)


def plan_bootstrap_workflow(
    target_dir: Path | None = None,
    dry_run: bool = True,
    aws_context: AwsExecutionContext | None = None,
) -> BootstrapPlanResult:
    """Inspect AWS resources and plan bootstrap actions without mutating AWS."""
    ctx = load_workspace_context(
        target_dir=target_dir,
        min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED,
    )
    workspace_dir, config = ctx.workspace_dir, ctx.config

    aws_ctx = aws_context or _resolve_bootstrap_aws_context(config)
    return _build_bootstrap_plan(
        workspace_dir=workspace_dir,
        config=config,
        imported=ctx.state.imported is True,
        aws_context=aws_ctx,
        dry_run=dry_run,
    )


def bootstrap_workspace_workflow(
    target_dir: Path | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> WorkspaceBootstrapResult:
    """Execute workspace bootstrap workflow and return structured result."""
    del force  # Force bypasses CLI confirmation; workflow itself is idempotent
    preparation = prepare_bootstrap_workflow(target_dir=target_dir, dry_run=dry_run)
    return apply_bootstrap_preparation(preparation=preparation, dry_run=dry_run)


def apply_bootstrap_preparation(
    *,
    preparation: BootstrapPreparation,
    dry_run: bool = False,
) -> WorkspaceBootstrapResult:
    """Apply a bootstrap plan using the AWS context that produced it."""
    plan = preparation.plan
    aws_context = preparation.aws_context

    if plan.codecommit_repo_planned_operation == "MISSING":
        raise LzaError(
            f"Configured CodeCommit configuration repository '{plan.codecommit_repo_name}' "
            "was not found. Imported resources must not be recreated automatically."
        )

    if dry_run:
        return WorkspaceBootstrapResult(
            workspace_dir=plan.workspace_dir,
            config=plan.config,
            aws_profile=plan.aws_profile,
            aws_region=plan.aws_region,
            account_id=plan.account_id,
            bucket_name=plan.bucket_name,
            codecommit_repo_name=plan.codecommit_repo_name,
            codecommit_branch_name=plan.codecommit_branch_name,
            codecommit_repo_planned_operation=plan.codecommit_repo_planned_operation,
            planned_operation=plan.planned_operation,
            dry_run=True,
            skipped=False,
            actions_taken=[],
        )

    # Reuse the workspace and authenticated AWS execution context from planning.
    workspace_dir = plan.workspace_dir
    config = plan.config
    state = load_workspace_state(workspace_dir)
    s3_client = aws_context.factory.get_client("s3")

    actions_taken = ensure_s3_workbench_assets_bucket(
        client=s3_client,
        bucket_name=plan.bucket_name,
        region=plan.aws_region,
    )

    if plan.codecommit_repo_name:
        cc_client = aws_context.factory.get_client("codecommit")
        if plan.codecommit_repo_planned_operation == "CREATE":
            ensure_codecommit_repository(
                client=cc_client,
                repository_name=plan.codecommit_repo_name,
                description="LZA Configuration Repository",
            )
            actions_taken.append(
                f"Created CodeCommit repository '{plan.codecommit_repo_name}' "
                f"in region '{plan.aws_region}'"
            )
        else:
            actions_taken.append(
                f"Reused existing CodeCommit repository '{plan.codecommit_repo_name}'"
            )

    # Persist assets bucket to lza-workspace.yaml
    config.assets_bucket = plan.bucket_name
    write_workspace_config(workspace_dir, config)

    # Persist operational bootstrap metadata to .lza/state.json.
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
        codecommit_repo_name=plan.codecommit_repo_name,
        codecommit_branch_name=plan.codecommit_branch_name,
        codecommit_repo_planned_operation=plan.codecommit_repo_planned_operation,
        planned_operation=plan.planned_operation,
        dry_run=False,
        skipped=False,
        actions_taken=actions_taken,
    )


__all__ = [
    "BootstrapPlanResult",
    "BootstrapPreparation",
    "WorkspaceBootstrapResult",
    "apply_bootstrap_preparation",
    "bootstrap_workspace_workflow",
    "ensure_s3_workbench_assets_bucket",
    "get_workbench_assets_bucket_name",
    "plan_bootstrap_workflow",
    "prepare_bootstrap_workflow",
]
