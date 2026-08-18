"""Workflow for planning LZA installer CloudFormation deployment."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.aws.cloudformation import inspect_cloudformation_stack
from lza_workbench.aws.codecommit import inspect_codecommit_repository
from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.aws.secrets_manager import inspect_github_secret_token
from lza_workbench.errors import LzaError
from lza_workbench.installer.config import validate_installer_configuration
from lza_workbench.installer.parameters import (
    build_installer_cfn_parameters,
)
from lza_workbench.installer.planning import (
    InstallerPlanResult,
    prepare_installer_plan_result,
)
from lza_workbench.installer.templates import (
    inspect_template_parameters,
    resolve_installer_template,
    validate_parameters_against_schema,
)
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context


def plan_installer_workflow(
    *,
    target_dir: Path | None = None,
    dry_run: bool = False,
) -> InstallerPlanResult:
    """Inspect AWS and return a plan for the persisted installer configuration."""
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.IMPORTED)
    workspace_dir, config = ctx.workspace_dir, ctx.config

    validation = validate_installer_configuration(config)
    if not validation.is_complete:
        missing = ", ".join(
            f"{field.section}.{field.attribute}" for field in validation.missing_fields
        )
        raise LzaError(
            f"Cannot create installer plan; required configuration is missing: {missing}. "
            "Run 'lza installer init' first."
        )

    template_path = resolve_installer_template(workspace_dir, config, dry_run=dry_run)
    params_schema = inspect_template_parameters(template_path)
    resolved_params = build_installer_cfn_parameters(config, schema=params_schema)
    validate_parameters_against_schema(resolved_params, params_schema)

    # Resolve AWS identity only after local configuration is complete and valid.
    aws_context = resolve_aws_execution_context(
        profile=config.aws.profile,
        region=config.aws.region,
        role_arn=config.aws.role_arn,
        expected_account_id=config.aws.account_id,
    )
    factory = aws_context.factory
    region = aws_context.region
    aws_identity = aws_context.identity
    aws_error = aws_context.error

    # Step 4: CodeCommit Source Planning
    codecommit_client = factory.get_client("codecommit") if aws_identity else None
    version_ref = resolved_params["RepositoryBranchName"]
    codecommit_plan = inspect_codecommit_repository(
        client=codecommit_client,
        repository_type=config.installer.source_code.repository_type,
        repository_name=config.installer.source_code.repository_name,
        branch_name=config.installer.source_code.branch,
        version_ref=version_ref,
        region=region,
    )

    # Check GitHub Secret if GitHub source is selected
    github_secret_warning = None
    if resolved_params.get("RepositorySource") == "github" and aws_identity:
        sm_client = factory.get_client("secretsmanager")
        if sm_client:
            github_secret_warning = inspect_github_secret_token(client=sm_client)

    # Step 5: CloudFormation Deployment Planning
    stack_name = config.installer.stack_name or "AWSAccelerator-InstallerStack"
    cfn_client = factory.get_client("cloudformation") if aws_identity else None
    cfn_plan = inspect_cloudformation_stack(
        client=cfn_client,
        stack_name=stack_name,
        resolved_parameters=resolved_params,
    )

    # Step 6: Return Structured Plan Result
    return prepare_installer_plan_result(
        workspace_dir=workspace_dir,
        config=config,
        region=region,
        aws_identity=aws_identity,
        aws_error=aws_error,
        codecommit_plan=codecommit_plan,
        cloudformation_plan=cfn_plan,
        dry_run=dry_run,
        github_secret_warning=github_secret_warning,
    )


__all__ = [
    "InstallerPlanResult",
    "plan_installer_workflow",
]
