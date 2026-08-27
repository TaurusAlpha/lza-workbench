"""Workflow for deploying the LZA installer CloudFormation stack."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lza_workbench.aws.cloudformation import (
    CfnDeploymentPlanResult,
    CfnStackStatusResult,
    delete_cloudformation_stack,
    deploy_cloudformation_stack,
    get_cloudformation_stack_status,
    inspect_cloudformation_stack,
    stream_cloudformation_stack_events,
)
from lza_workbench.aws.context import AwsExecutionContext, resolve_aws_execution_context
from lza_workbench.aws.s3 import get_s3_https_url, inspect_s3_bucket, upload_s3_file
from lza_workbench.errors import LzaError
from lza_workbench.installer.deployment import (
    InstallerConfigValidationError,
    InstallerConfigValidationResult,
    get_installer_template_digest,
    include_template_digest_change,
    inspect_installer_source,
    prepare_installer_template,
    validate_cloudformation_plan,
    validate_deployment_preflight,
)
from lza_workbench.installer.state import (
    record_installer_deployment,
    record_installer_deployment_failure,
)
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context
from lza_workbench.workspace.schema import WorkspaceConfig
from lza_workbench.workspace.state import load_workspace_state, write_workspace_state


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
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.CONFIGURED)
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
    if not insp["exists"]:
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
    "apply_installer_deployment",
    "deploy_installer_workflow",
    "prepare_installer_deployment",
]
