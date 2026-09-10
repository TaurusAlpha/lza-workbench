"""Workflow and operations for deploying the LZA installer CloudFormation stack."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from lza_workbench.errors import LzaError
from lza_workbench.infrastructure.aws.cloudformation import (
    CfnDeploymentPlanResult,
    CfnStackStatusResult,
    delete_cloudformation_stack,
    deploy_cloudformation_stack,
    get_cloudformation_stack_status,
    inspect_cloudformation_stack,
    stream_cloudformation_stack_events,
)
from lza_workbench.infrastructure.aws.codecommit import inspect_codecommit_repository
from lza_workbench.infrastructure.aws.s3 import (
    get_s3_https_url,
    inspect_s3_bucket,
    inspect_s3_object,
    upload_s3_file,
)
from lza_workbench.infrastructure.aws.secrets_manager import inspect_secret_exists
from lza_workbench.infrastructure.aws.session import (
    AwsClientFactory,
    AwsExecutionContext,
    resolve_aws_execution_context,
)
from lza_workbench.installer.config import (
    InstallerConfigValidationResult,
    validate_installer_configuration,
)
from lza_workbench.installer.parameters import (
    build_installer_cfn_parameters,
    resolve_installer_source_branch,
)
from lza_workbench.installer.source import (
    CodeCommitPlanResult,
    github_secret_warning,
    prepare_codecommit_source_plan,
)
from lza_workbench.installer.state import (
    record_installer_deployment,
    record_installer_deployment_failure,
)
from lza_workbench.installer.templates import (
    inspect_template_parameters,
    resolve_installer_template,
    validate_parameters_against_schema,
)
from lza_workbench.workspace.context import WorkspaceCapability, load_workspace_context
from lza_workbench.workspace.persistence import load_workspace_state, write_workspace_state
from lza_workbench.workspace.schema import WorkspaceConfig

SAFE_EXISTING_STACK_STATUSES = {
    "CREATE_COMPLETE",
    "UPDATE_COMPLETE",
    "UPDATE_ROLLBACK_COMPLETE",
    "ROLLBACK_COMPLETE",
}

SAFE_CREATE_STACK_STATUSES = {"ROLLBACK_COMPLETE", "DELETE_COMPLETE", None}


class InstallerConfigValidationError(LzaError):
    """Raised when installer configuration is incomplete for deployment."""

    def __init__(self, validation: InstallerConfigValidationResult) -> None:
        self.validation = validation
        missing = ", ".join(f"{s.section}.{s.attribute}" for s in validation.missing_fields)
        super().__init__(
            f"{len(validation.missing_fields)} required parameter(s) missing from "
            f"lza-workspace.yaml ({missing}). "
            "Run 'lza installer plan' to resolve and configure missing values."
        )


def validate_deployment_preflight(config: WorkspaceConfig) -> None:
    """Validate workspace installer settings before executing deployment mutations."""
    validation = validate_installer_configuration(config)
    if not validation.is_complete:
        raise InstallerConfigValidationError(validation)
    if not (config.assets_bucket or "").strip():
        raise LzaError(
            "Workbench assets bucket is not configured in lza-workspace.yaml. "
            "Run 'lza bootstrap' to create and configure the required assets bucket "
            "before deploying the installer."
        )


def prepare_installer_template(
    *, workspace_dir: Path, config: WorkspaceConfig, dry_run: bool
) -> tuple[Path, dict[str, str]]:
    """Resolve and validate the local template and its parameters against the schema."""
    template_path = resolve_installer_template(workspace_dir, config, dry_run=dry_run)
    schema = inspect_template_parameters(template_path)
    parameters = build_installer_cfn_parameters(config, schema=schema)
    validate_parameters_against_schema(parameters, schema)
    return template_path, parameters


def get_installer_template_digest(template_path: Path) -> str:
    """Return a stable digest for a resolved installer template."""
    try:
        return sha256(template_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise LzaError(f"Unable to read installer template {template_path}: {exc}") from exc


def include_template_digest_change(
    plan: CfnDeploymentPlanResult,
    *,
    template_digest: str,
    deployed_template_digest: str | None,
) -> CfnDeploymentPlanResult:
    """Mark a parameter-stable stack for update when its template changed."""
    if plan.operation != "NO_CHANGE" or deployed_template_digest == template_digest:
        return plan
    return replace(plan, operation="UPDATE")


def inspect_installer_source(
    *,
    factory: AwsClientFactory,
    config: WorkspaceConfig,
    region: str,
) -> CodeCommitPlanResult | None:
    """Validate required remote source preconditions for installer CloudFormation."""
    source = config.installer.source_code
    if source.repository_type == "codecommit":
        version_ref = resolve_installer_source_branch(
            source.repository_type, source.branch, config.lza.version
        )
        observation = inspect_codecommit_repository(
            client=factory.get_client("codecommit"),
            repository_name=source.repository_name or "aws-accelerator-codecommit",
            branch_name=source.branch or version_ref,
        )
        plan = prepare_codecommit_source_plan(
            repository_type="codecommit",
            repository_name=source.repository_name,
            branch_name=source.branch,
            version_ref=version_ref,
            region=region,
            observation=observation,
        )
        if plan.status != "INITIALIZED":
            raise LzaError(
                "CodeCommit source is a manual prerequisite: repository "
                f"'{plan.repository_name}' must contain branch '{plan.branch_name}' before "
                "installer deployment. Run 'lza installer plan' for the required source actions."
            )
        return plan

    if source.repository_type == "s3":
        inspect_s3_object(
            client=factory.get_client("s3"),
            bucket_name=source.bucket or "",
            object_key=source.key or "",
        )
    elif source.repository_type == "github":
        exists, error = inspect_secret_exists(
            client=factory.get_client("secretsmanager"),
            secret_name=source.github_secret_name,
        )
        warning = github_secret_warning(source.github_secret_name, exists, error)
        if warning:
            raise LzaError(warning)
        return None
    return None


def validate_cloudformation_plan(plan: CfnDeploymentPlanResult) -> str:
    """Return a safe mutation operation or reject an unknown/unsafe stack state."""
    if plan.stack_status == "ROLLBACK_COMPLETE":
        return "CREATE"
    if (
        plan.operation in {"CREATE", "NO_CHANGE"}
        and plan.stack_status in SAFE_CREATE_STACK_STATUSES
    ):
        return "CREATE"
    if (
        plan.operation in {"UPDATE", "NO_CHANGE"}
        and plan.stack_status in SAFE_EXISTING_STACK_STATUSES
    ):
        return "UPDATE" if plan.operation == "UPDATE" else "NO_CHANGE"
    raise LzaError(
        "Refusing CloudFormation deployment because the stack state is unsafe or unknown: "
        f"operation={plan.operation}, status={plan.stack_status or 'not found'}."
    )


@dataclass(frozen=True)
class InstallerDeployResult:
    """Structured result of installer deployment workflow."""

    workspace_dir: Path
    stack_name: str
    operation: str
    cfn_plan: CfnDeploymentPlanResult
    stack_id: str | None
    final_status: CfnStackStatusResult | None
    dry_run: bool
    skipped: bool
    profile: str = ""
    region: str = ""
    account_id: str = ""


@dataclass(frozen=True)
class InstallerDeploymentPreparation:
    """Validated deployment inputs prepared once for review and execution."""

    workspace_dir: Path
    config: WorkspaceConfig
    aws_context: AwsExecutionContext
    template_path: Path
    template_digest: str
    resolved_parameters: dict[str, str]
    stack_name: str
    operation: str
    cfn_plan: CfnDeploymentPlanResult
    profile: str
    account_id: str


def prepare_installer_deployment(
    *,
    target_dir: Path | None = None,
    dry_run: bool = False,
) -> InstallerDeploymentPreparation:
    """Prepare one validated installer deployment for confirmation and application."""
    ctx = load_workspace_context(
        target_dir,
        required_capabilities=(
            WorkspaceCapability.METADATA_VALID,
            WorkspaceCapability.CONFIGURATION_PRESENT,
            WorkspaceCapability.INSTALLER_CONFIGURED,
        ),
    )
    workspace_dir, config = ctx.workspace_dir, ctx.config
    profile = config.aws.profile or ""

    validate_deployment_preflight(config)

    try:
        aws_context = resolve_aws_execution_context(
            profile=config.aws.profile,
            region=config.aws.region,
            role_arn=config.aws.role_arn,
            expected_account_id=config.aws.account_id,
            require_identity=True,
            require_expected_account=True,
            prime_credentials=config.aws.prime_credentials,
        )
    except LzaError:
        raise
    except Exception as exc:
        raise LzaError(f"AWS identity resolution failed: {exc}") from exc
    assert aws_context.identity is not None
    account_id = aws_context.identity["account"]

    template_path, resolved_parameters = prepare_installer_template(
        workspace_dir=workspace_dir, config=config, dry_run=dry_run
    )
    template_digest = get_installer_template_digest(template_path)
    inspect_installer_source(factory=aws_context.factory, config=config, region=aws_context.region)

    stack_name = config.installer.stack_name or "AWSAccelerator-InstallerStack"
    cfn_plan = inspect_cloudformation_stack(
        client=aws_context.factory.get_client("cloudformation"),
        stack_name=stack_name,
        resolved_parameters=resolved_parameters,
    )
    state = load_workspace_state(workspace_dir)
    cfn_plan = include_template_digest_change(
        cfn_plan,
        template_digest=template_digest,
        deployed_template_digest=state.installer_template_digest,
    )
    operation = validate_cloudformation_plan(cfn_plan)

    return InstallerDeploymentPreparation(
        workspace_dir=workspace_dir,
        config=config,
        aws_context=aws_context,
        template_path=template_path,
        template_digest=template_digest,
        resolved_parameters=resolved_parameters,
        stack_name=stack_name,
        operation=operation,
        cfn_plan=cfn_plan,
        profile=profile,
        account_id=account_id,
    )


def deploy_installer_workflow(
    *,
    target_dir: Path | None = None,
    dry_run: bool = False,
    force: bool = False,
    force_no_change: bool = False,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> InstallerDeployResult:
    """Execute the installer deployment workflow and return structured results."""
    preparation = prepare_installer_deployment(target_dir=target_dir, dry_run=dry_run)
    return apply_installer_deployment(
        preparation=preparation,
        dry_run=dry_run,
        force=force,
        force_no_change=force_no_change,
        on_event=on_event,
    )


def apply_installer_deployment(
    *,
    preparation: InstallerDeploymentPreparation,
    dry_run: bool = False,
    force: bool = False,
    force_no_change: bool = False,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> InstallerDeployResult:
    """Apply a previously prepared installer deployment without repeating discovery."""
    workspace_dir = preparation.workspace_dir
    config = preparation.config
    aws_context = preparation.aws_context
    operation = preparation.operation
    assert aws_context.identity is not None

    if operation == "NO_CHANGE" and not force and not force_no_change:
        return InstallerDeployResult(
            workspace_dir=workspace_dir,
            stack_name=preparation.stack_name,
            operation=operation,
            cfn_plan=preparation.cfn_plan,
            stack_id=None,
            final_status=None,
            dry_run=dry_run,
            skipped=True,
            profile=preparation.profile,
            region=aws_context.region,
            account_id=preparation.account_id,
        )

    if operation == "NO_CHANGE" and (force or force_no_change):
        operation = "UPDATE"

    if dry_run:
        return InstallerDeployResult(
            workspace_dir=workspace_dir,
            stack_name=preparation.stack_name,
            operation=operation,
            cfn_plan=preparation.cfn_plan,
            stack_id=None,
            final_status=None,
            dry_run=True,
            skipped=False,
            profile=preparation.profile,
            region=aws_context.region,
            account_id=preparation.account_id,
        )
    if operation == "CREATE" and preparation.cfn_plan.stack_status == "ROLLBACK_COMPLETE":
        delete_cloudformation_stack(
            client=aws_context.factory.get_client("cloudformation"),
            stack_name=preparation.stack_name,
        )

    s3_client = aws_context.factory.get_client("s3")
    bucket_name = (config.assets_bucket or "").strip()
    insp = inspect_s3_bucket(client=s3_client, bucket_name=bucket_name)
    if not insp.exists:
        raise LzaError(
            f"Configured assets bucket '{bucket_name}' does not exist in AWS. "
            "Run 'lza bootstrap' to create and configure the required AWS resources."
        )

    s3_key = f"installer-templates/{config.lza.version}/AWSAccelerator-InstallerStack.template"
    upload_s3_file(
        client=s3_client,
        file_path=preparation.template_path,
        bucket_name=bucket_name,
        object_key=s3_key,
    )
    template_url = get_s3_https_url(
        bucket_name=bucket_name, object_key=s3_key, region=aws_context.region
    )

    stack_id = deploy_cloudformation_stack(
        client=aws_context.factory.get_client("cloudformation"),
        stack_name=preparation.stack_name,
        template_url=template_url,
        parameters=preparation.resolved_parameters,
        operation=operation,
    )

    cfn_client = aws_context.factory.get_client("cloudformation")
    final_status = (
        get_cloudformation_stack_status(client=cfn_client, stack_name=preparation.stack_name)
        if stack_id is None
        else stream_cloudformation_stack_events(
            client=cfn_client,
            stack_name=preparation.stack_name,
            on_event=on_event,
        )
    )

    if final_status.stack_status not in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}:
        state = load_workspace_state(workspace_dir)
        record_installer_deployment_failure(
            state,
            aws_identity=aws_context.identity,
            stack_id=final_status.stack_id or stack_id,
            stack_status=final_status.stack_status or "UNKNOWN",
        )
        write_workspace_state(workspace_dir, state)
        status_name = final_status.stack_status or "UNKNOWN"
        error_detail = f": {final_status.error}" if final_status.error else ""
        raise LzaError(
            f"CloudFormation stack deployment failed with status ({status_name}){error_detail}"
        )

    state = load_workspace_state(workspace_dir)
    downloaded_at = (
        datetime.fromtimestamp(preparation.template_path.stat().st_mtime, tz=UTC)
        if preparation.template_path.exists()
        else None
    )
    record_installer_deployment(
        state,
        aws_identity=aws_context.identity,
        stack_id=final_status.stack_id or stack_id,
        stack_status=final_status.stack_status or "CREATE_COMPLETE",
        template_version=config.lza.version,
        template_digest=preparation.template_digest,
        downloaded_at=downloaded_at,
    )
    write_workspace_state(workspace_dir, state)

    return InstallerDeployResult(
        workspace_dir=workspace_dir,
        stack_name=preparation.stack_name,
        operation=operation,
        cfn_plan=preparation.cfn_plan,
        stack_id=stack_id,
        final_status=final_status,
        dry_run=False,
        skipped=stack_id is None,
        profile=preparation.profile,
        region=aws_context.region,
        account_id=preparation.account_id,
    )


__all__ = [
    "CfnDeploymentPlanResult",
    "CfnStackStatusResult",
    "InstallerConfigValidationError",
    "InstallerConfigValidationResult",
    "InstallerDeploymentPreparation",
    "InstallerDeployResult",
    "SAFE_CREATE_STACK_STATUSES",
    "SAFE_EXISTING_STACK_STATUSES",
    "apply_installer_deployment",
    "deploy_installer_workflow",
    "get_installer_template_digest",
    "include_template_digest_change",
    "inspect_installer_source",
    "prepare_installer_deployment",
    "prepare_installer_template",
    "validate_cloudformation_plan",
    "validate_deployment_preflight",
]
