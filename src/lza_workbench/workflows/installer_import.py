"""Workflow for discovering and importing live AWS installer deployment parameters."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lza_workbench.aws.cloudformation import (
    CfnStackStatusResult,
    get_cloudformation_stack_status,
)
from lza_workbench.aws.codepipeline import (
    PipelineStateResult,
    get_pipeline_state,
)
from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.errors import LzaError
from lza_workbench.installer.sync import sync_installer_config, sync_installer_state
from lza_workbench.installer.versions import branch_to_version
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context
from lza_workbench.workspace.schema import WorkspaceConfig, WorkspaceState


@dataclass(frozen=True)
class InstallerImportResult:
    """Structured result of installer import workflow."""

    workspace_dir: Path
    config: WorkspaceConfig
    state: WorkspaceState
    stack_name: str
    cfn_status: CfnStackStatusResult
    deployed_version: str
    aws_identity: dict[str, str] | None
    aws_error: str | None
    dry_run: bool
    pipeline_state: PipelineStateResult | None = None
    applied_parameters: dict[str, str] = field(default_factory=dict)


def import_installer_workflow(
    *,
    target_dir: Path | None = None,
    stack_name: str | None = None,
    dry_run: bool = False,
) -> InstallerImportResult:
    """Query live CloudFormation installer stack and synchronize local workspace configuration."""
    ctx = load_workspace_context(
        target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED
    )
    workspace_dir, config, state = ctx.workspace_dir, ctx.config, ctx.state

    resolved_stack_name = (
        stack_name or config.installer.stack_name or "AWSAccelerator-InstallerStack"
    ).strip()
    if not resolved_stack_name:
        resolved_stack_name = "AWSAccelerator-InstallerStack"

    config.installer.stack_name = resolved_stack_name

    aws_context = resolve_aws_execution_context(
        profile=config.aws.profile,
        region=config.aws.region,
        role_arn=config.aws.role_arn,
        expected_account_id=config.aws.account_id,
        prime_credentials=config.aws.prime_credentials,
        require_identity=True,
    )
    cfn_client = (
        aws_context.factory.get_client("cloudformation") if aws_context.identity else None
    )
    cfn_status = get_cloudformation_stack_status(
        client=cfn_client, stack_name=resolved_stack_name
    )

    if not cfn_status.exists:
        raise LzaError(
            f"CloudFormation installer stack '{resolved_stack_name}' was not found "
            f"in region '{aws_context.region}' for profile '{config.aws.profile}'."
        )

    deployed_version = branch_to_version(
        cfn_status.deployed_parameters.get("RepositoryBranchName", "")
    )

    prefix = config.lza.accelerator_prefix or "AWSAccelerator"
    installer_pipeline_name = (
        config.pipelines.installer.name or f"{prefix}-Installer"
    )
    codepipeline_client = (
        aws_context.factory.get_client("codepipeline") if aws_context.identity else None
    )
    pipeline_state = get_pipeline_state(
        client=codepipeline_client, pipeline_name=installer_pipeline_name
    )

    if not dry_run:
        config = sync_installer_config(
            workspace_dir=workspace_dir,
            config=config,
            cfn_status=cfn_status,
        )
        state = sync_installer_state(
            workspace_dir=workspace_dir,
            state=state,
            cfn_status=cfn_status,
            deployed_version=deployed_version,
        )

    return InstallerImportResult(
        workspace_dir=workspace_dir,
        config=config,
        state=state,
        stack_name=resolved_stack_name,
        cfn_status=cfn_status,
        deployed_version=deployed_version,
        aws_identity=aws_context.identity,
        aws_error=aws_context.error,
        dry_run=dry_run,
        pipeline_state=pipeline_state,
        applied_parameters=dict(cfn_status.deployed_parameters),
    )


__all__ = [
    "InstallerImportResult",
    "import_installer_workflow",
]
