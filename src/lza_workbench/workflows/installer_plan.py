"""Workflow for planning LZA installer CloudFormation deployment."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.aws.cloudformation import inspect_cloudformation_stack
from lza_workbench.aws.codecommit import inspect_codecommit_repository
from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.errors import LzaError
from lza_workbench.installer.config import validate_installer_configuration
from lza_workbench.installer.parameters import build_installer_cfn_parameters
from lza_workbench.installer.planning import (
    InstallerPlanResult,
    prepare_installer_plan_result,
)
from lza_workbench.installer.templates import (
    inspect_template_parameters,
    resolve_installer_template,
    validate_parameters_against_schema,
)
from lza_workbench.installer.versions import version_to_branch
from lza_workbench.workspace.config import write_workspace_config
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context


def plan_installer_workflow(
    *,
    target_dir: Path | None = None,
    dry_run: bool = False,
    no_save: bool = False,
) -> InstallerPlanResult:
    """Execute the installer planning workflow and return structured results."""
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.IMPORTED)
    workspace_dir, config = ctx.workspace_dir, ctx.config

    # Validate required installer configuration parameters in workspace
    validation = validate_installer_configuration(config)
    if not validation.is_complete:
        raise LzaError(
            f"{len(validation.missing_fields)} required parameter(s) missing from "
            "lza-workspace.yaml. "
            "Update lza-workspace.yaml with required values."
        )

    # Save accepted installer settings if requested and not dry run
    if not no_save and not dry_run:
        write_workspace_config(workspace_dir, config)

    # Step 1: Resolve Template & Schema
    template_path = resolve_installer_template(workspace_dir, config, dry_run=dry_run)
    params_schema = inspect_template_parameters(template_path)

    # Step 2: Validate Resolved Parameters against Template Schema
    resolved_params = build_installer_cfn_parameters(config)
    validate_parameters_against_schema(resolved_params, params_schema)

    # Step 3: Create AWS Factory & Validate Profile Identity
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
    version_ref = version_to_branch(config.lza.version)
    codecommit_plan = inspect_codecommit_repository(
        client=codecommit_client,
        repository_type=config.installer.source_code.repository_type,
        repository_name=config.installer.source_code.repository_name,
        branch_name=config.installer.source_code.branch,
        version_ref=version_ref,
        region=region,
    )

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
    )


__all__ = [
    "InstallerPlanResult",
    "plan_installer_workflow",
]
