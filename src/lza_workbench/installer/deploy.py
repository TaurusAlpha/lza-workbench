"""Workflow and operations for deploying the LZA installer CloudFormation stack."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
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
from lza_workbench.infrastructure.aws.s3 import (
    S3BucketObservation,
    create_s3_bucket,
    get_s3_https_url,
    inspect_s3_bucket,
    put_s3_bucket_tags,
    put_s3_bucket_versioning,
    upload_s3_file,
)
from lza_workbench.infrastructure.aws.session import (
    AwsExecutionContext,
    resolve_aws_execution_context,
)
from lza_workbench.installer.schema import LzaInstaller
from lza_workbench.installer.source import (
    inspect_installer_source,
)
from lza_workbench.installer.state import (
    record_installer_deployment,
    record_installer_deployment_failure,
)
from lza_workbench.installer.templates import (
    get_installer_template_digest,
    include_template_digest_change,
    prepare_installer_template,
)
from lza_workbench.installer.validation import (
    SAFE_CREATE_STACK_STATUSES,
    SAFE_EXISTING_STACK_STATUSES,
    InstallerConfigValidationError,
    InstallerConfigValidationResult,
    validate_cloudformation_plan,
    validate_deployment_preflight,
)
from lza_workbench.workspace.context import load_workspace_context
from lza_workbench.workspace.persistence import (
    load_workspace_state,
    update_workspace_state,
    write_workspace_config,
)
from lza_workbench.workspace.schema import (
    CustomerEnvironmentTarget,
    WorkspaceConfig,
)
from lza_workbench.workspace.validation import WorkspaceCapability


@dataclass(frozen=True)
class InstallerDeployResult:
    workspace_dir: Path | None
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

    workspace_dir: Path | None
    config: WorkspaceConfig | None
    aws_context: AwsExecutionContext
    template_path: Path
    template_digest: str
    resolved_parameters: dict[str, str]
    stack_name: str
    operation: str
    cfn_plan: CfnDeploymentPlanResult
    profile: str
    account_id: str
    artifact_bucket: str = ""
    artifact_bucket_observation: S3BucketObservation | None = None
    artifact_bucket_operation: str = "CREATE"
    environment_target: CustomerEnvironmentTarget | None = None
    installer: LzaInstaller | None = None

    def __post_init__(self) -> None:
        if self.environment_target is None and self.config is not None:
            object.__setattr__(self, "environment_target", self.config.environment_target)
        if self.installer is None and self.config is not None:
            object.__setattr__(self, "installer", self.config.installer)


def prepare_installer_deployment(
    *,
    target_dir: Path | None = None,
    environment_target: CustomerEnvironmentTarget | None = None,
    installer: LzaInstaller | None = None,
    config: WorkspaceConfig | None = None,
    workspace_dir: Path | None = None,
    template_path: Path | None = None,
    aws_context: AwsExecutionContext | None = None,
    deployed_template_digest: str | None = None,
    dry_run: bool = False,
) -> InstallerDeploymentPreparation:
    """Prepare one validated installer deployment for confirmation and application."""
    if environment_target is not None and installer is not None:
        resolved_workspace_dir = workspace_dir
        resolved_config = config
        resolved_target = environment_target
        resolved_installer = installer
    elif config is not None:
        resolved_workspace_dir = workspace_dir
        resolved_config = config
        resolved_target = environment_target or config.environment_target
        resolved_installer = installer or config.installer
    else:
        ctx = load_workspace_context(
            target_dir,
            required_capabilities=(
                WorkspaceCapability.METADATA_VALID,
                WorkspaceCapability.INSTALLER_CONFIGURED,
            ),
            include_state=False,
        )
        resolved_workspace_dir, resolved_config = ctx.workspace_dir, ctx.config
        resolved_target = environment_target or ctx.config.environment_target
        resolved_installer = installer or ctx.config.installer
    profile = (
        resolved_config.aws.profile
        if resolved_config is not None
        else (aws_context.factory.profile if aws_context is not None else None)
    ) or ""

    validate_deployment_preflight(
        resolved_config,
        installer=resolved_installer,
        environment_target=resolved_target,
    )

    if aws_context is not None:
        resolved_aws = aws_context
    else:
        try:
            resolved_aws = resolve_aws_execution_context(
                profile=profile or None,
                region=resolved_target.region,
                role_arn=resolved_config.aws.role_arn if resolved_config is not None else None,
                expected_account_id=resolved_target.account_id,
                require_identity=True,
                require_expected_account=True,
                prime_credentials=(
                    resolved_config.aws.prime_credentials if resolved_config is not None else False
                ),
            )
        except LzaError:
            raise
        except Exception as exc:
            raise LzaError(f"AWS identity resolution failed: {exc}") from exc
    resolved_aws.require_live(expected_account_id=resolved_target.account_id)
    assert resolved_aws.identity is not None
    account_id = resolved_aws.identity["account"]

    configured_assets_bucket = (
        resolved_target.assets_bucket
        if resolved_target.assets_bucket is not None
        else (resolved_config.assets_bucket if resolved_config is not None else None)
    )
    artifact_bucket = (configured_assets_bucket or "").strip() or (
        f"s3-lza-workbench-assets-{account_id}-{resolved_aws.region}"
    )
    artifact_bucket_observation = inspect_s3_bucket(
        client=resolved_aws.factory.get_client("s3"), bucket_name=artifact_bucket
    )
    if artifact_bucket_observation.exists:
        managed_by = artifact_bucket_observation.tags.get("ManagedBy")
        workspace_slug = artifact_bucket_observation.tags.get("Workspace")
        if managed_by and (
            managed_by != "lza-workbench" or workspace_slug != resolved_target.customer.slug
        ):
            raise LzaError(
                f"S3 bucket '{artifact_bucket}' is tagged for another Workbench workspace "
                "or owner; refusing to adopt it."
            )
    artifact_bucket_operation = (
        "CREATE"
        if not artifact_bucket_observation.exists
        else "UPDATE"
        if not artifact_bucket_observation.versioning_enabled
        else "NO_CHANGE"
    )

    if template_path is None and resolved_workspace_dir is None:
        raise LzaError("Installer deployment requires either template_path or workspace_dir.")
    resolved_template_path, resolved_parameters = prepare_installer_template(
        config=resolved_config,
        installer=resolved_installer,
        environment_target=resolved_target,
        workspace_dir=resolved_workspace_dir,
        template_path=template_path,
        dry_run=dry_run,
    )

    template_digest = get_installer_template_digest(resolved_template_path)
    inspect_installer_source(
        factory=resolved_aws.factory,
        config=resolved_config,
        installer=resolved_installer,
        environment_target=resolved_target,
        region=resolved_aws.region,
    )

    stack_name = resolved_target.installer_stack_name or "AWSAccelerator-InstallerStack"
    cfn_plan = inspect_cloudformation_stack(
        client=resolved_aws.factory.get_client("cloudformation"),
        stack_name=stack_name,
        resolved_parameters=resolved_parameters,
    )
    if deployed_template_digest is not None:
        resolved_deployed_digest = deployed_template_digest
    elif resolved_workspace_dir is not None:
        state = load_workspace_state(resolved_workspace_dir)
        resolved_deployed_digest = state.installer.template.digest
    else:
        resolved_deployed_digest = None

    cfn_plan = include_template_digest_change(
        cfn_plan,
        template_digest=template_digest,
        deployed_template_digest=resolved_deployed_digest,
    )
    operation = validate_cloudformation_plan(cfn_plan)

    return InstallerDeploymentPreparation(
        workspace_dir=resolved_workspace_dir,
        config=resolved_config,
        aws_context=resolved_aws,
        template_path=resolved_template_path,
        template_digest=template_digest,
        resolved_parameters=resolved_parameters,
        stack_name=stack_name,
        operation=operation,
        cfn_plan=cfn_plan,
        profile=profile,
        account_id=account_id,
        artifact_bucket=artifact_bucket,
        artifact_bucket_observation=artifact_bucket_observation,
        artifact_bucket_operation=artifact_bucket_operation,
        environment_target=resolved_target,
        installer=resolved_installer,
    )


def deploy_installer_workflow(
    *,
    target_dir: Path | None = None,
    environment_target: CustomerEnvironmentTarget | None = None,
    installer: LzaInstaller | None = None,
    config: WorkspaceConfig | None = None,
    workspace_dir: Path | None = None,
    template_path: Path | None = None,
    aws_context: AwsExecutionContext | None = None,
    deployed_template_digest: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    force_no_change: bool = False,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> InstallerDeployResult:
    """Execute the installer deployment workflow and return structured results."""
    preparation = prepare_installer_deployment(
        target_dir=target_dir,
        environment_target=environment_target,
        installer=installer,
        config=config,
        workspace_dir=workspace_dir,
        template_path=template_path,
        aws_context=aws_context,
        deployed_template_digest=deployed_template_digest,
        dry_run=dry_run,
    )
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
    env_target = preparation.environment_target or (
        config.environment_target if config is not None else None
    )
    if env_target is None:
        raise ValueError(
            "apply_installer_deployment requires preparation with environment_target or config."
        )
    aws_context = preparation.aws_context
    operation = preparation.operation
    aws_context.require_live(expected_account_id=env_target.account_id)
    assert aws_context.identity is not None

    if (
        operation == "NO_CHANGE"
        and preparation.artifact_bucket_operation == "NO_CHANGE"
        and not force
        and not force_no_change
    ):
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
    bucket_name = preparation.artifact_bucket
    insp = preparation.artifact_bucket_observation or inspect_s3_bucket(
        client=s3_client, bucket_name=bucket_name
    )
    actions_taken: list[str] = []
    if not insp.exists:
        create_s3_bucket(client=s3_client, bucket_name=bucket_name, region=aws_context.region)
        put_s3_bucket_tags(
            client=s3_client,
            bucket_name=bucket_name,
            tags={
                "ManagedBy": "lza-workbench",
                "Workspace": env_target.customer.slug,
                "Purpose": "installer-artifacts",
            },
        )
        actions_taken.append(f"Created installer artifact bucket '{bucket_name}'")
    if not insp.versioning_enabled:
        put_s3_bucket_versioning(client=s3_client, bucket_name=bucket_name, enabled=True)
        actions_taken.append(f"Enabled versioning on installer artifact bucket '{bucket_name}'")
    if insp.exists and not actions_taken:
        actions_taken.append(f"Reused installer artifact bucket '{bucket_name}'")

    s3_key = f"installer-templates/{env_target.lza.version}/AWSAccelerator-InstallerStack.template"
    upload_s3_file(
        client=s3_client,
        file_path=preparation.template_path,
        bucket_name=bucket_name,
        object_key=s3_key,
    )
    if not env_target.assets_bucket:
        env_target.assets_bucket = bucket_name
    if config is not None and not config.assets_bucket:
        config.assets_bucket = bucket_name
        if workspace_dir is not None:
            write_workspace_config(workspace_dir, config)
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
        if workspace_dir is not None:
            update_workspace_state(
                workspace_dir,
                lambda current: record_installer_deployment_failure(
                    current,
                    aws_identity=aws_context.identity,
                    operation=operation,
                    stack_name=preparation.stack_name,
                    stack_id=final_status.stack_id or stack_id,
                    stack_status=final_status.stack_status or "UNKNOWN",
                    template_version=env_target.lza.version,
                    template_digest=preparation.template_digest,
                    error=final_status.error,
                ),
            )
        status_name = final_status.stack_status or "UNKNOWN"
        error_detail = f": {final_status.error}" if final_status.error else ""
        raise LzaError(
            f"CloudFormation stack deployment failed with status ({status_name}){error_detail}"
        )

    if workspace_dir is not None:
        downloaded_at = (
            datetime.fromtimestamp(preparation.template_path.stat().st_mtime, tz=UTC)
            if preparation.template_path.exists()
            else None
        )
        update_workspace_state(
            workspace_dir,
            lambda current: record_installer_deployment(
                current,
                aws_identity=aws_context.identity,
                operation=operation,
                stack_name=preparation.stack_name,
                stack_id=final_status.stack_id or stack_id,
                stack_status=final_status.stack_status or "CREATE_COMPLETE",
                template_version=env_target.lza.version,
                template_digest=preparation.template_digest,
                deployed_parameters=dict(
                    final_status.deployed_parameters or preparation.resolved_parameters
                ),
                downloaded_at=downloaded_at,
            ),
        )

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
