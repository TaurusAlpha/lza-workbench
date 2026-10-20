"""Workflow and result models for planning LZA installer CloudFormation deployment."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lza_workbench.errors import LzaError
from lza_workbench.infrastructure.aws.cloudformation import (
    CfnDeploymentPlanResult,
    inspect_cloudformation_stack,
)
from lza_workbench.infrastructure.aws.codecommit import (
    CodeCommitRepositoryStatus,
    inspect_codecommit_repository,
)
from lza_workbench.infrastructure.aws.s3 import inspect_s3_bucket
from lza_workbench.infrastructure.aws.secrets_manager import inspect_secret_exists
from lza_workbench.infrastructure.aws.session import (
    AwsExecutionContext,
    resolve_aws_execution_context,
)
from lza_workbench.installer.schema import LzaInstaller
from lza_workbench.installer.source import (
    CodeCommitPlanResult,
    build_github_secret_warning,
    prepare_codecommit_source_plan,
)
from lza_workbench.installer.templates import (
    get_installer_template_digest,
    include_template_digest_change,
    prepare_installer_template,
)
from lza_workbench.installer.validation import validate_installer_configuration
from lza_workbench.workspace.context import load_workspace_context
from lza_workbench.workspace.schema import CustomerEnvironmentTarget, WorkspaceConfig
from lza_workbench.workspace.validation import WorkspaceCapability


@dataclass(frozen=True)
class InstallerPlanResult:
    workspace_dir: Path | None
    config: WorkspaceConfig | None
    profile: str
    region: str
    aws_identity: dict[str, str] | None
    aws_error: str | None
    codecommit_plan: CodeCommitPlanResult
    cloudformation_plan: CfnDeploymentPlanResult
    dry_run: bool
    github_secret_warning: str | None = None
    artifact_bucket: str | None = None
    artifact_bucket_operation: str = "CREATE"
    environment_target: CustomerEnvironmentTarget | None = None
    installer: LzaInstaller | None = None

    def __post_init__(self) -> None:
        if self.environment_target is None and self.config is not None:
            object.__setattr__(self, "environment_target", self.config.environment_target)
        if self.installer is None and self.config is not None:
            object.__setattr__(self, "installer", self.config.installer)


def prepare_installer_plan_result(
    *,
    workspace_dir: Path | None,
    config: WorkspaceConfig | None = None,
    environment_target: CustomerEnvironmentTarget | None = None,
    installer: LzaInstaller | None = None,
    profile: str | None = None,
    region: str,
    aws_identity: dict[str, str] | None,
    aws_error: str | None,
    codecommit_plan: CodeCommitPlanResult,
    cloudformation_plan: CfnDeploymentPlanResult,
    dry_run: bool,
    github_secret_warning: str | None = None,
    artifact_bucket: str | None = None,
    artifact_bucket_operation: str = "CREATE",
) -> InstallerPlanResult:
    """Collect command results into the presentation-independent plan result."""
    resolved_target = environment_target or (
        config.environment_target if config is not None else None
    )
    resolved_installer = installer or (config.installer if config is not None else None)
    resolved_profile = (
        profile
        if profile is not None
        else (config.aws.profile if config is not None else "") or ""
    )
    return InstallerPlanResult(
        workspace_dir=workspace_dir,
        config=config,
        profile=resolved_profile,
        region=region,
        aws_identity=aws_identity,
        aws_error=aws_error,
        codecommit_plan=codecommit_plan,
        cloudformation_plan=cloudformation_plan,
        dry_run=dry_run,
        github_secret_warning=github_secret_warning,
        artifact_bucket=artifact_bucket,
        artifact_bucket_operation=artifact_bucket_operation,
        environment_target=resolved_target,
        installer=resolved_installer,
    )


def plan_installer_workflow(
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
) -> InstallerPlanResult:
    if environment_target is not None and installer is not None:
        resolved_workspace_dir = workspace_dir
        resolved_config = config
        resolved_target = environment_target
        resolved_installer = installer
        resolved_deployed_digest = deployed_template_digest
    elif config is not None:
        resolved_workspace_dir = workspace_dir
        resolved_config = config
        resolved_target = environment_target or config.environment_target
        resolved_installer = installer or config.installer
        resolved_deployed_digest = deployed_template_digest
    else:
        ctx = load_workspace_context(
            target_dir,
            required_capabilities=(WorkspaceCapability.METADATA_VALID,),
        )
        resolved_workspace_dir = ctx.workspace_dir
        resolved_config = ctx.config
        resolved_target = environment_target or ctx.config.environment_target
        resolved_installer = installer or ctx.config.installer
        resolved_deployed_digest = (
            deployed_template_digest
            if deployed_template_digest is not None
            else ctx.state.installer.template.digest
        )

    validation = validate_installer_configuration(
        resolved_config,
        installer=resolved_installer,
        environment_target=resolved_target,
    )
    if not validation.is_complete:
        missing = ", ".join(
            f"{field.section}.{field.attribute}" for field in validation.missing_fields
        )
        raise LzaError(
            f"Cannot create installer plan; required configuration is missing: {missing}. "
            "Run 'lza installer init' first."
        )

    resolved_template_path, resolved_params = prepare_installer_template(
        config=resolved_config,
        installer=resolved_installer,
        environment_target=resolved_target,
        workspace_dir=resolved_workspace_dir,
        template_path=template_path,
        dry_run=True,
    )
    template_digest = get_installer_template_digest(resolved_template_path)

    # Resolve AWS identity only after installer specification is complete and valid.
    profile = (
        resolved_config.aws.profile
        if resolved_config is not None
        else (aws_context.factory.profile if aws_context is not None else None)
    )
    resolved_aws = aws_context or resolve_aws_execution_context(
        profile=profile,
        region=resolved_target.region,
        role_arn=resolved_config.aws.role_arn if resolved_config is not None else None,
        expected_account_id=resolved_target.account_id,
        prime_credentials=(
            resolved_config.aws.prime_credentials if resolved_config is not None else False
        ),
    )
    factory = resolved_aws.factory
    region = resolved_aws.region
    aws_identity = resolved_aws.identity
    aws_error = resolved_aws.error

    configured_assets_bucket = (
        resolved_target.assets_bucket
        if resolved_target.assets_bucket is not None
        else (resolved_config.assets_bucket if resolved_config is not None else None)
    )
    artifact_bucket = (configured_assets_bucket or "").strip() or (
        f"s3-lza-workbench-assets-{aws_identity['account']}-{region}"
    ) if aws_identity else (configured_assets_bucket or "")
    if aws_identity:
        artifact_observation = inspect_s3_bucket(
            client=factory.get_client("s3"), bucket_name=artifact_bucket
        )
        artifact_bucket_operation = (
            "CREATE" if not artifact_observation.exists else
            "UPDATE" if not artifact_observation.versioning_enabled else "NO_CHANGE"
        )
    else:
        artifact_bucket_operation = "UNKNOWN"

    # CodeCommit Source Planning
    codecommit_client = factory.get_client("codecommit") if aws_identity else None
    version_ref = resolved_params["RepositoryBranchName"]
    source_code = resolved_installer.source_code
    repo_name = source_code.repository_name or "aws-accelerator-codecommit"
    branch_name = source_code.branch or version_ref
    if codecommit_client is not None:
        codecommit_observation = inspect_codecommit_repository(
            client=codecommit_client,
            repository_name=repo_name,
            branch_name=branch_name,
        )
    else:
        codecommit_observation = CodeCommitRepositoryStatus(
            repository_name=repo_name,
            branch_name=branch_name,
            exists=False,
            accessible=False,
            branch_exists=False,
            error="No AWS client available",
        )
    codecommit_plan = prepare_codecommit_source_plan(
        repository_type=source_code.repository_type,
        repository_name=source_code.repository_name,
        branch_name=source_code.branch,
        version_ref=version_ref,
        region=region,
        observation=codecommit_observation
        if source_code.repository_type == "codecommit"
        else None,
    )

    # Check GitHub Secret if GitHub source is selected
    github_secret_warning = None
    if resolved_params.get("RepositorySource") == "github" and aws_identity:
        sm_client = factory.get_client("secretsmanager")
        if sm_client:
            exists, error = inspect_secret_exists(
                client=sm_client,
                secret_name=source_code.github_secret_name,
            )
            github_secret_warning = build_github_secret_warning(
                source_code.github_secret_name, exists, error
            )

    # CloudFormation Deployment Planning
    stack_name = resolved_target.installer_stack_name or "AWSAccelerator-InstallerStack"
    cfn_client = factory.get_client("cloudformation") if aws_identity else None
    if cfn_client is not None:
        cfn_plan = inspect_cloudformation_stack(
            client=cfn_client,
            stack_name=stack_name,
            resolved_parameters=resolved_params,
        )
    else:
        cfn_plan = CfnDeploymentPlanResult(
            stack_name=stack_name,
            operation="CREATE",
            stack_status=None,
            resolved_parameters=resolved_params,
        )
    cfn_plan = include_template_digest_change(
        cfn_plan,
        template_digest=template_digest,
        deployed_template_digest=resolved_deployed_digest,
    )

    # Return Structured Plan Result
    return prepare_installer_plan_result(
        workspace_dir=resolved_workspace_dir,
        config=resolved_config,
        environment_target=resolved_target,
        installer=resolved_installer,
        profile=profile or "",
        region=region,
        aws_identity=aws_identity,
        aws_error=aws_error,
        codecommit_plan=codecommit_plan,
        cloudformation_plan=cfn_plan,
        dry_run=dry_run,
        github_secret_warning=github_secret_warning,
        artifact_bucket=artifact_bucket or None,
        artifact_bucket_operation=artifact_bucket_operation,
    )


__all__ = [
    "InstallerPlanResult",
    "plan_installer_workflow",
    "prepare_installer_plan_result",
]
