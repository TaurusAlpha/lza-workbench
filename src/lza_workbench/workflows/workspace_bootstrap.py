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
from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.aws.s3 import (
    create_s3_bucket,
    inspect_s3_bucket,
    put_s3_bucket_encryption,
    put_s3_bucket_versioning,
)
from lza_workbench.errors import LzaError
from lza_workbench.workspace.config import write_workspace_config
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context
from lza_workbench.workspace.schema import WorkspaceConfig
from lza_workbench.workspace.state import write_workspace_state


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

    # Inspect CodeCommit configuration repository if configured
    is_codecommit_config = (
        config.configuration.repository.type == "codecommit"
        or config.installer.options.configuration_repository_location == "codecommit"
    )

    cc_repo_name: str | None = None
    cc_branch_name: str | None = None
    cc_repo_exists = False
    cc_branch_exists = False
    cc_planned_op = "N/A"

    if is_codecommit_config:
        cc_repo_name = (
            config.configuration.repository.repository_name
            or config.installer.options.existing_config_repository_name
            or "lza-config-source"
        )
        cc_branch_name = (
            config.configuration.repository.branch
            or config.installer.options.existing_config_repository_branch_name
            or "main"
        )
        cc_client = aws_ctx.factory.get_client("codecommit")
        cc_insp = inspect_codecommit_config_repository(
            client=cc_client,
            repository_name=cc_repo_name,
            branch_name=cc_branch_name,
        )
        cc_repo_exists = cc_insp["exists"]
        cc_branch_exists = cc_insp["branch_exists"]

        is_imported = config.configuration.template.source == "local"

        if is_imported:
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
        else:
            if cc_repo_exists:
                cc_planned_op = "NO_CHANGE"
                actions.append(
                    f"Reuse existing CodeCommit repository '{cc_repo_name}'"
                )
            else:
                cc_planned_op = "CREATE"
                actions.append(
                    f"Create CodeCommit repository '{cc_repo_name}' in region '{region}'"
                )

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


def bootstrap_workspace_workflow(
    target_dir: Path | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> WorkspaceBootstrapResult:
    """Execute workspace bootstrap workflow and return structured result."""
    del force  # Force bypasses CLI confirmation; workflow itself is idempotent
    plan = plan_bootstrap_workflow(target_dir=target_dir, dry_run=dry_run)

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

    if plan.codecommit_repo_name:
        cc_client = aws_ctx.factory.get_client("codecommit")
        if plan.codecommit_repo_planned_operation == "CREATE":
            ensure_codecommit_repository(
                client=cc_client,
                repository_name=plan.codecommit_repo_name,
                branch_name=plan.codecommit_branch_name or "main",
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
    "WorkspaceBootstrapResult",
    "bootstrap_workspace_workflow",
    "ensure_s3_workbench_assets_bucket",
    "get_workbench_assets_bucket_name",
    "plan_bootstrap_workflow",
]
