"""Workflow for bootstrapping LZA Workbench AWS prerequisite resources."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lza_workbench.aws.codecommit import (
    ensure_codecommit_repository,
    inspect_codecommit_repository,
)
from lza_workbench.aws.context import AwsExecutionContext, resolve_aws_execution_context
from lza_workbench.aws.s3 import (
    create_s3_bucket,
    inspect_s3_bucket,
    put_s3_bucket_encryption,
    put_s3_bucket_versioning,
)
from lza_workbench.aws.secrets_manager import (
    create_or_update_secret,
    inspect_secret_details,
)
from lza_workbench.errors import LzaError
from lza_workbench.installer.parameters import resolve_installer_source_branch
from lza_workbench.installer.source import validate_github_repository_access
from lza_workbench.workspace.config import write_workspace_config
from lza_workbench.workspace.context import (
    WorkspaceCapability,
    WorkspaceContext,
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

    if not insp.exists:
        create_s3_bucket(client=client, bucket_name=bucket_name, region=region)
        actions_taken.append(f"Created S3 bucket '{bucket_name}' in region '{region}'")

    if not insp.versioning_enabled:
        put_s3_bucket_versioning(client=client, bucket_name=bucket_name, enabled=True)
        actions_taken.append(f"Enabled versioning on S3 bucket '{bucket_name}'")

    if not insp.kms_encrypted:
        put_s3_bucket_encryption(client=client, bucket_name=bucket_name)
        actions_taken.append(f"Enabled AWS-managed KMS encryption on S3 bucket '{bucket_name}'")

    if not actions_taken:
        actions_taken.append(f"Reused existing S3 assets bucket '{bucket_name}'")

    return actions_taken


@dataclass(frozen=True)
class BootstrapAction:
    """One plain-language bootstrap action for CLI or Web presentation."""

    subject: str
    operation: str
    message: str
    severity: str | None = None


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
    github_secret_name: str | None
    github_secret_exists: bool
    github_secret_accessible: bool
    github_repo_owner: str | None
    github_repo_name: str | None
    github_repo_branch: str | None
    github_repo_accessible: bool
    github_planned_operation: str
    planned_operation: str
    actions: list[BootstrapAction]
    warnings: list[str]
    dry_run: bool
    imported: bool = False
    is_live: bool = True
    error: str | None = None


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
    github_secret_name: str | None
    github_secret_created: bool
    github_repo_owner: str | None
    github_repo_name: str | None
    github_repo_branch: str | None
    github_repo_accessible: bool
    github_planned_operation: str
    planned_operation: str
    dry_run: bool
    skipped: bool
    actions_taken: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class BootstrapPreparation:
    """Resolved workspace, AWS context, and plan for one bootstrap execution."""

    context: WorkspaceContext
    aws_context: AwsExecutionContext
    plan: BootstrapPlanResult


def _resolve_bootstrap_aws_context(
    config: WorkspaceConfig,
    require_identity: bool = True,
) -> AwsExecutionContext:
    """Resolve the authenticated AWS target required for bootstrap operations."""
    try:
        return resolve_aws_execution_context(
            profile=config.aws.profile,
            region=config.aws.region,
            role_arn=config.aws.role_arn,
            expected_account_id=config.aws.account_id,
            require_identity=require_identity,
            require_expected_account=require_identity,
            prime_credentials=config.aws.prime_credentials,
        )
    except LzaError:
        raise
    except Exception as exc:
        raise LzaError(f"AWS identity resolution failed: {exc}") from exc


def _resolve_offline_codecommit_params(
    config: WorkspaceConfig,
) -> tuple[str | None, str | None]:
    if config.configuration.repository.type != "codecommit":
        return None, None
    repo_name = config.configuration.repository.repository_name or "lza-config-source"
    branch_name = config.configuration.repository.branch or "main"
    return repo_name, branch_name


def _resolve_offline_github_params(
    config: WorkspaceConfig,
) -> tuple[str | None, str | None, str | None, str | None]:
    if config.installer.source_code.repository_type != "github":
        return None, None, None, None
    secret_name = config.installer.source_code.github_secret_name or "accelerator/github-token"
    owner = config.installer.source_code.owner or "awslabs"
    repo_name = config.installer.source_code.repository_name or "landing-zone-accelerator-on-aws"
    branch = config.installer.source_code.branch or resolve_installer_source_branch(
        "github", None, config.lza.version
    )
    return secret_name, owner, repo_name, branch


def _build_offline_bootstrap_plan(
    *,
    workspace_dir: Path,
    config: WorkspaceConfig,
    imported: bool,
    aws_ctx: AwsExecutionContext,
    dry_run: bool,
) -> BootstrapPlanResult:
    account_id = config.aws.account_id or "Unknown"
    region = aws_ctx.region or config.aws.region or "Unknown"
    profile = config.aws.profile or ""
    bucket_name = (
        get_workbench_assets_bucket_name(account_id, region)
        if account_id != "Unknown" and region != "Unknown"
        else f"lza-workbench-assets-{region}"
    )
    cc_repo_name, cc_branch_name = _resolve_offline_codecommit_params(config)
    (
        gh_secret_name,
        gh_repo_owner,
        gh_repo_name,
        gh_repo_branch,
    ) = _resolve_offline_github_params(config)
    is_github_source = config.installer.source_code.repository_type == "github"

    return BootstrapPlanResult(
        workspace_dir=workspace_dir,
        config=config,
        aws_profile=profile,
        aws_region=region,
        account_id=account_id,
        bucket_name=bucket_name,
        bucket_exists=False,
        versioning_enabled=False,
        encryption_enabled=False,
        bucket_planned_operation="OFFLINE",
        codecommit_repo_name=cc_repo_name,
        codecommit_branch_name=cc_branch_name,
        codecommit_repo_exists=False,
        codecommit_branch_exists=False,
        codecommit_repo_planned_operation="OFFLINE" if cc_repo_name else "N/A",
        github_secret_name=gh_secret_name,
        github_secret_exists=False,
        github_secret_accessible=False,
        github_repo_owner=gh_repo_owner,
        github_repo_name=gh_repo_name,
        github_repo_branch=gh_repo_branch,
        github_repo_accessible=False,
        github_planned_operation="OFFLINE" if is_github_source else "N/A",
        planned_operation="OFFLINE",
        actions=[],
        warnings=[
            (
                f"AWS is offline: {aws_ctx.error or 'Authentication required'}. "
                "Displayed prerequisite resource plans are not live."
            )
        ],
        dry_run=dry_run,
        imported=imported,
        is_live=False,
        error=aws_ctx.error,
    )


def _plan_s3_bootstrap(
    *,
    s3_client: Any,
    bucket_name: str,
    region: str,
    actions: list[BootstrapAction],
) -> tuple[Any, str]:
    insp = inspect_s3_bucket(client=s3_client, bucket_name=bucket_name)
    if not insp.exists:
        bucket_planned_operation = "CREATE"
        actions.append(
            BootstrapAction(
                subject=bucket_name,
                operation="CREATE",
                message=f"Create S3 bucket in region '{region}'",
            )
        )
    else:
        initial_actions_count = len(actions)
        if not insp.versioning_enabled:
            actions.append(
                BootstrapAction(
                    subject=bucket_name,
                    operation="UPDATE",
                    message="Enable versioning on S3 bucket",
                )
            )
        if not insp.kms_encrypted:
            actions.append(
                BootstrapAction(
                    subject=bucket_name,
                    operation="UPDATE",
                    message="Enable AWS-managed KMS encryption on S3 bucket",
                )
            )

        if len(actions) > initial_actions_count:
            bucket_planned_operation = "UPDATE"
        else:
            bucket_planned_operation = "NO_CHANGE"
            actions.append(
                BootstrapAction(
                    subject=bucket_name,
                    operation="NO_CHANGE",
                    message="Reuse existing S3 assets bucket (already configured)",
                )
            )
    return insp, bucket_planned_operation


def _plan_codecommit_bootstrap(
    *,
    config: WorkspaceConfig,
    aws_ctx: AwsExecutionContext,
    region: str,
    imported: bool,
    actions: list[BootstrapAction],
) -> tuple[str | None, str | None, bool, bool, str]:
    is_codecommit_config = config.configuration.repository.type == "codecommit"
    if not is_codecommit_config:
        return None, None, False, False, "N/A"

    cc_repo_name = config.configuration.repository.repository_name or "lza-config-source"
    cc_branch_name = config.configuration.repository.branch or "main"
    cc_client = aws_ctx.factory.get_client("codecommit")
    cc_insp = inspect_codecommit_repository(
        client=cc_client,
        repository_name=cc_repo_name,
        branch_name=cc_branch_name,
    )
    cc_repo_exists = cc_insp.exists
    cc_branch_exists = cc_insp.branch_exists

    if not cc_insp.accessible and not cc_insp.not_found:
        raise LzaError(
            f"Unable to access configured CodeCommit repository '{cc_repo_name}': "
            f"{cc_insp.error or 'unknown error'}"
        )

    if imported:
        if cc_repo_exists:
            cc_planned_op = "NO_CHANGE"
            actions.append(
                BootstrapAction(
                    subject=cc_repo_name,
                    operation="NO_CHANGE",
                    message=f"Validate existing CodeCommit repository branch '{cc_branch_name}' (imported)",
                )
            )
        else:
            cc_planned_op = "MISSING"
            actions.append(
                BootstrapAction(
                    subject=cc_repo_name,
                    operation="MISSING",
                    message=(
                        "CodeCommit repository not found "
                        "(imported resources must not be recreated automatically)"
                    ),
                    severity="error",
                )
            )
    elif cc_repo_exists:
        cc_planned_op = "NO_CHANGE"
        actions.append(
            BootstrapAction(
                subject=cc_repo_name,
                operation="NO_CHANGE",
                message="Reuse existing CodeCommit repository",
            )
        )
    else:
        cc_planned_op = "CREATE"
        actions.append(
            BootstrapAction(
                subject=cc_repo_name,
                operation="CREATE",
                message=f"Create CodeCommit repository in region '{region}'",
            )
        )

    return cc_repo_name, cc_branch_name, cc_repo_exists, cc_branch_exists, cc_planned_op


def _plan_existing_github_secret(
    *,
    github_secret_name: str,
    github_repo_owner: str,
    github_repo_name: str,
    github_repo_branch: str,
    github_secret_accessible: bool,
    token_val: str | None,
    secret_error: str | None,
    actions: list[BootstrapAction],
) -> tuple[bool, str]:
    actions.append(
        BootstrapAction(
            subject=github_secret_name,
            operation="NO_CHANGE",
            message="Validate AWS Secrets Manager secret (exists)",
        )
    )
    if github_secret_accessible or token_val:
        gh_res = validate_github_repository_access(
            owner=github_repo_owner,
            repository_name=github_repo_name,
            branch=github_repo_branch,
            token=token_val,
        )
        if gh_res["accessible"]:
            actions.append(
                BootstrapAction(
                    subject=f"{github_repo_owner}/{github_repo_name}",
                    operation="NO_CHANGE",
                    message=f"Validate GitHub repository branch '{github_repo_branch}' (accessible)",
                )
            )
            return True, "NO_CHANGE"
        actions.append(
            BootstrapAction(
                subject=f"{github_repo_owner}/{github_repo_name}",
                operation="INACCESSIBLE",
                message=f"GitHub repository access failed: {gh_res['error']}",
                severity="error",
            )
        )
        return False, "INACCESSIBLE"

    actions.append(
        BootstrapAction(
            subject=github_secret_name,
            operation="INACCESSIBLE",
            message=f"AWS Secrets Manager secret access failed: {secret_error}",
            severity="error",
        )
    )
    return False, "INACCESSIBLE"


def _plan_new_github_token(
    *,
    github_secret_name: str,
    github_repo_owner: str,
    github_repo_name: str,
    github_repo_branch: str,
    token: str,
    actions: list[BootstrapAction],
    warnings: list[str],
) -> tuple[bool, str]:
    actions.append(
        BootstrapAction(
            subject=github_secret_name,
            operation="CREATE",
            message="Create AWS Secrets Manager secret with provided token",
        )
    )
    gh_res = validate_github_repository_access(
        owner=github_repo_owner,
        repository_name=github_repo_name,
        branch=github_repo_branch,
        token=token,
    )
    if gh_res["accessible"]:
        actions.append(
            BootstrapAction(
                subject=f"{github_repo_owner}/{github_repo_name}",
                operation="NO_CHANGE",
                message=f"Validate GitHub repository branch '{github_repo_branch}' (accessible)",
            )
        )
        return True, "CREATE"

    warning_msg = (
        f"GitHub repository '{github_repo_owner}/{github_repo_name}' "
        f"check returned: {gh_res['error']}"
    )
    warnings.append(warning_msg)
    actions.append(
        BootstrapAction(
            subject=github_secret_name,
            operation="WARNING",
            message=warning_msg,
            severity="warning",
        )
    )
    return False, "CREATE"


def _plan_missing_github_secret(
    *,
    github_secret_name: str,
    allow_missing_github_secret: bool,
    actions: list[BootstrapAction],
    warnings: list[str],
) -> tuple[bool, str]:
    if allow_missing_github_secret:
        warning_msg = (
            f"AWS Secrets Manager secret '{github_secret_name}' was not found. "
            "You must create this secret containing a valid GitHub token before "
            "deploying the installer."
        )
        warnings.append(warning_msg)
        actions.append(
            BootstrapAction(
                subject=github_secret_name,
                operation="WARNING",
                message=(
                    "AWS Secrets Manager secret not found "
                    "(proceeding as requested; manual secret creation required)"
                ),
                severity="warning",
            )
        )
        return False, "WARNING"

    actions.append(
        BootstrapAction(
            subject=github_secret_name,
            operation="MISSING",
            message="AWS Secrets Manager secret not found",
            severity="error",
        )
    )
    actions.append(
        BootstrapAction(
            subject=github_secret_name,
            operation="MISSING",
            message="AWS LZA requires a GitHub token stored in this Secrets Manager secret",
            severity="error",
        )
    )
    return False, "MISSING"


def _plan_github_bootstrap(
    *,
    config: WorkspaceConfig,
    aws_ctx: AwsExecutionContext,
    github_token: str | None,
    allow_missing_github_secret: bool,
    actions: list[BootstrapAction],
    warnings: list[str],
) -> tuple[str | None, bool, bool, str | None, str | None, str | None, bool, str]:
    is_github_source = config.installer.source_code.repository_type == "github"
    if not is_github_source:
        return None, False, False, None, None, None, False, "N/A"

    github_secret_name = (
        config.installer.source_code.github_secret_name or "accelerator/github-token"
    )
    github_repo_owner = config.installer.source_code.owner or "awslabs"
    github_repo_name = (
        config.installer.source_code.repository_name or "landing-zone-accelerator-on-aws"
    )
    github_repo_branch = config.installer.source_code.branch or resolve_installer_source_branch(
        "github", None, config.lza.version
    )
    sm_client = aws_ctx.factory.get_client("secretsmanager")
    secret_details = inspect_secret_details(
        client=sm_client, secret_name=github_secret_name
    )
    github_secret_exists = secret_details.exists
    github_secret_accessible = secret_details.accessible
    token_val = (github_token or "").strip() or secret_details.value

    if github_secret_exists:
        github_repo_accessible, github_planned_op = _plan_existing_github_secret(
            github_secret_name=github_secret_name,
            github_repo_owner=github_repo_owner,
            github_repo_name=github_repo_name,
            github_repo_branch=github_repo_branch,
            github_secret_accessible=github_secret_accessible,
            token_val=token_val,
            secret_error=secret_details.error,
            actions=actions,
        )
    elif github_token and github_token.strip():
        github_repo_accessible, github_planned_op = _plan_new_github_token(
            github_secret_name=github_secret_name,
            github_repo_owner=github_repo_owner,
            github_repo_name=github_repo_name,
            github_repo_branch=github_repo_branch,
            token=github_token.strip(),
            actions=actions,
            warnings=warnings,
        )
    else:
        github_repo_accessible, github_planned_op = _plan_missing_github_secret(
            github_secret_name=github_secret_name,
            allow_missing_github_secret=allow_missing_github_secret,
            actions=actions,
            warnings=warnings,
        )

    return (
        github_secret_name,
        github_secret_exists,
        github_secret_accessible,
        github_repo_owner,
        github_repo_name,
        github_repo_branch,
        github_repo_accessible,
        github_planned_op,
    )


def _resolve_overall_planned_operation(
    *,
    bucket_planned_operation: str,
    cc_planned_op: str,
    github_planned_op: str,
    allow_missing_github_secret: bool,
) -> str:
    if cc_planned_op == "MISSING" or (
        github_planned_op in {"MISSING", "INACCESSIBLE"} and not allow_missing_github_secret
    ):
        return "MISSING"
    if (
        bucket_planned_operation == "CREATE"
        or cc_planned_op == "CREATE"
        or github_planned_op == "CREATE"
    ):
        return "CREATE"
    if bucket_planned_operation == "UPDATE" or cc_planned_op == "UPDATE":
        return "UPDATE"
    return "NO_CHANGE"


def _build_bootstrap_plan(
    *,
    workspace_dir: Path,
    config: WorkspaceConfig,
    imported: bool,
    aws_context: AwsExecutionContext,
    dry_run: bool,
    github_token: str | None = None,
    allow_missing_github_secret: bool = False,
) -> BootstrapPlanResult:
    """Inspect bootstrap resources using one resolved workspace and AWS context."""
    if not aws_context.is_live:
        return _build_offline_bootstrap_plan(
            workspace_dir=workspace_dir,
            config=config,
            imported=imported,
            aws_ctx=aws_context,
            dry_run=dry_run,
        )

    assert aws_context.identity is not None
    account_id = aws_context.identity["account"]
    region = aws_context.region
    profile = config.aws.profile or ""

    bucket_name = get_workbench_assets_bucket_name(account_id, region)
    s3_client = aws_context.factory.get_client("s3")

    actions: list[BootstrapAction] = []
    warnings: list[str] = []

    insp, bucket_planned_operation = _plan_s3_bootstrap(
        s3_client=s3_client,
        bucket_name=bucket_name,
        region=region,
        actions=actions,
    )

    cc_repo_name, cc_branch_name, cc_repo_exists, cc_branch_exists, cc_planned_op = (
        _plan_codecommit_bootstrap(
            config=config,
            aws_ctx=aws_context,
            region=region,
            imported=imported,
            actions=actions,
        )
    )

    (
        github_secret_name,
        github_secret_exists,
        github_secret_accessible,
        github_repo_owner,
        github_repo_name,
        github_repo_branch,
        github_repo_accessible,
        github_planned_op,
    ) = _plan_github_bootstrap(
        config=config,
        aws_ctx=aws_context,
        github_token=github_token,
        allow_missing_github_secret=allow_missing_github_secret,
        actions=actions,
        warnings=warnings,
    )

    overall_planned_operation = _resolve_overall_planned_operation(
        bucket_planned_operation=bucket_planned_operation,
        cc_planned_op=cc_planned_op,
        github_planned_op=github_planned_op,
        allow_missing_github_secret=allow_missing_github_secret,
    )

    return BootstrapPlanResult(
        workspace_dir=workspace_dir,
        config=config,
        aws_profile=profile,
        aws_region=region,
        account_id=account_id,
        bucket_name=bucket_name,
        bucket_exists=insp.exists,
        versioning_enabled=insp.versioning_enabled,
        encryption_enabled=insp.kms_encrypted,
        bucket_planned_operation=bucket_planned_operation,
        codecommit_repo_name=cc_repo_name,
        codecommit_branch_name=cc_branch_name,
        codecommit_repo_exists=cc_repo_exists,
        codecommit_branch_exists=cc_branch_exists,
        codecommit_repo_planned_operation=cc_planned_op,
        github_secret_name=github_secret_name,
        github_secret_exists=github_secret_exists,
        github_secret_accessible=github_secret_accessible,
        github_repo_owner=github_repo_owner,
        github_repo_name=github_repo_name,
        github_repo_branch=github_repo_branch,
        github_repo_accessible=github_repo_accessible,
        github_planned_operation=github_planned_op,
        planned_operation=overall_planned_operation,
        actions=actions,
        warnings=warnings,
        dry_run=dry_run,
        imported=imported,
        is_live=True,
        error=None,
    )


def prepare_bootstrap_workflow(
    target_dir: Path | None = None,
    dry_run: bool = False,
    github_token: str | None = None,
    allow_missing_github_secret: bool = False,
) -> BootstrapPreparation:
    """Resolve one workspace and AWS target for bootstrap planning and execution."""
    context = load_workspace_context(
        target_dir=target_dir,
        required_capabilities=(WorkspaceCapability.METADATA_VALID,),
    )
    aws_context = _resolve_bootstrap_aws_context(context.config, require_identity=True)
    plan = _build_bootstrap_plan(
        workspace_dir=context.workspace_dir,
        config=context.config,
        imported=context.state.imported is True,
        aws_context=aws_context,
        dry_run=dry_run,
        github_token=github_token,
        allow_missing_github_secret=allow_missing_github_secret,
    )
    return BootstrapPreparation(context=context, aws_context=aws_context, plan=plan)


def plan_bootstrap_workflow(
    target_dir: Path | None = None,
    dry_run: bool = True,
    aws_context: AwsExecutionContext | None = None,
    github_token: str | None = None,
    allow_missing_github_secret: bool = False,
    require_identity: bool = False,
) -> BootstrapPlanResult:
    """Inspect AWS resources and plan bootstrap actions without mutating AWS."""
    ctx = load_workspace_context(
        target_dir=target_dir,
        required_capabilities=(WorkspaceCapability.METADATA_VALID,),
    )
    workspace_dir, config = ctx.workspace_dir, ctx.config

    aws_ctx = aws_context or _resolve_bootstrap_aws_context(
        config, require_identity=require_identity
    )
    return _build_bootstrap_plan(
        workspace_dir=workspace_dir,
        config=config,
        imported=ctx.state.imported is True,
        aws_context=aws_ctx,
        dry_run=dry_run,
        github_token=github_token,
        allow_missing_github_secret=allow_missing_github_secret,
    )


def bootstrap_workspace_workflow(
    target_dir: Path | None = None,
    dry_run: bool = False,
    force: bool = False,
    github_token: str | None = None,
    allow_missing_github_secret: bool = False,
) -> WorkspaceBootstrapResult:
    """Execute workspace bootstrap workflow and return structured result."""
    del force  # Force bypasses CLI confirmation; workflow itself is idempotent
    preparation = prepare_bootstrap_workflow(
        target_dir=target_dir,
        dry_run=dry_run,
        github_token=github_token,
        allow_missing_github_secret=allow_missing_github_secret,
    )
    return apply_bootstrap_preparation(
        preparation=preparation,
        dry_run=dry_run,
        github_token=github_token,
        allow_missing_github_secret=allow_missing_github_secret,
    )


def apply_bootstrap_preparation(
    *,
    preparation: BootstrapPreparation,
    dry_run: bool = False,
    github_token: str | None = None,
    allow_missing_github_secret: bool = False,
) -> WorkspaceBootstrapResult:
    """Apply a bootstrap plan using the AWS context that produced it."""
    plan = preparation.plan
    aws_context = preparation.aws_context

    if not aws_context.is_live:
        raise LzaError(
            f"Cannot apply bootstrap changes: AWS is offline ({aws_context.error or 'Authentication required'})."
        )

    if plan.codecommit_repo_planned_operation == "MISSING":
        raise LzaError(
            f"Configured CodeCommit configuration repository '{plan.codecommit_repo_name}' "
            "was not found. Imported resources must not be recreated automatically."
        )

    if (
        plan.github_planned_operation in {"MISSING", "INACCESSIBLE"}
        and not allow_missing_github_secret
    ):
        raise LzaError(
            "GitHub installer source prerequisite validation failed for "
            f"'{plan.github_secret_name}'. Ensure the secret exists in Secrets Manager "
            "with a valid token, or pass --github-token / --allow-missing-github-secret."
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
            github_secret_name=plan.github_secret_name,
            github_secret_created=False,
            github_repo_owner=plan.github_repo_owner,
            github_repo_name=plan.github_repo_name,
            github_repo_branch=plan.github_repo_branch,
            github_repo_accessible=plan.github_repo_accessible,
            github_planned_operation=plan.github_planned_operation,
            planned_operation=plan.planned_operation,
            dry_run=True,
            skipped=False,
            actions_taken=[],
            warnings=list(plan.warnings),
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

    github_secret_created = False
    if plan.github_secret_name:
        sm_client = aws_context.factory.get_client("secretsmanager")
        if plan.github_planned_operation == "CREATE" and github_token:
            create_or_update_secret(
                client=sm_client,
                secret_name=plan.github_secret_name,
                secret_value=github_token.strip(),
                description="AWS Accelerator GitHub Token",
            )
            github_secret_created = True
            actions_taken.append(
                f"Created AWS Secrets Manager secret '{plan.github_secret_name}' with GitHub token"
            )
        elif plan.github_planned_operation == "NO_CHANGE":
            actions_taken.append(
                f"Validated GitHub token secret '{plan.github_secret_name}' and repository "
                f"'{plan.github_repo_owner}/{plan.github_repo_name}'"
            )
        elif plan.github_planned_operation == "WARNING":
            actions_taken.append(
                f"Skipped missing AWS Secrets Manager secret '{plan.github_secret_name}' "
                "(manual creation required)"
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
        github_secret_name=plan.github_secret_name,
        github_secret_created=github_secret_created,
        github_repo_owner=plan.github_repo_owner,
        github_repo_name=plan.github_repo_name,
        github_repo_branch=plan.github_repo_branch,
        github_repo_accessible=plan.github_repo_accessible,
        github_planned_operation=plan.github_planned_operation,
        planned_operation=plan.planned_operation,
        dry_run=False,
        skipped=False,
        actions_taken=actions_taken,
        warnings=list(plan.warnings),
    )


__all__ = [
    "BootstrapAction",
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
