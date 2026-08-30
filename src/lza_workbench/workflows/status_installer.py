"""Workflow for querying installer stack status."""

from __future__ import annotations

from dataclasses import dataclass
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
from lza_workbench.installer.status import (
    StateAlignment,
    calculate_configuration_drift,
    calculate_state_alignment,
)
from lza_workbench.installer.versions import branch_to_version, normalize_lza_version
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context
from lza_workbench.workspace.schema import WorkspaceConfig, WorkspaceState


@dataclass(frozen=True)
class InstallerStatusResult:
    """All data required to render an installer status report."""

    workspace_dir: Path
    config: WorkspaceConfig
    state: WorkspaceState | None
    profile: str
    region: str
    aws_identity: dict[str, str] | None
    aws_error: str | None
    cfn_status: CfnStackStatusResult
    deployed_version: str
    configuration_drift: dict[str, tuple[str, str]]
    state_alignment: StateAlignment | None
    installer_pipeline_name: str
    pipeline_state: PipelineStateResult | None = None


def prepare_installer_status(
    *,
    workspace_dir: Path,
    config: WorkspaceConfig,
    state: WorkspaceState | None,
    profile: str,
    region: str,
    aws_identity: dict[str, str] | None,
    aws_error: str | None,
    cfn_status: CfnStackStatusResult,
    pipeline_state: PipelineStateResult | None = None,
) -> InstallerStatusResult:
    """Prepare report data without calling AWS, writing files, or rendering output."""
    deployed_version = branch_to_version(
        cfn_status.deployed_parameters.get("RepositoryBranchName", "") if cfn_status.exists else ""
    )
    drift = (
        calculate_configuration_drift(config, cfn_status.deployed_parameters)
        if cfn_status.exists and cfn_status.deployed_parameters
        else {}
    )
    alignment = (
        calculate_state_alignment(
            state,
            stack_id=cfn_status.stack_id,
            stack_status=cfn_status.stack_status,
            deployed_version=deployed_version,
        )
        if state and cfn_status.exists
        else None
    )
    prefix = config.lza.accelerator_prefix or "AWSAccelerator"
    installer_pipeline_name = config.pipelines.installer.name or f"{prefix}-Installer"
    resolved_pipeline_state = pipeline_state or PipelineStateResult(
        pipeline_name=installer_pipeline_name,
        exists=False,
        status="NOT_CHECKED",
    )
    return InstallerStatusResult(
        workspace_dir=workspace_dir,
        config=config,
        state=state,
        profile=profile,
        region=region,
        aws_identity=aws_identity,
        aws_error=aws_error,
        cfn_status=cfn_status,
        deployed_version=deployed_version,
        configuration_drift=drift,
        state_alignment=alignment,
        installer_pipeline_name=installer_pipeline_name,
        pipeline_state=resolved_pipeline_state,
    )


def get_installer_status_workflow(
    *,
    target_dir: Path | None = None,
    config: WorkspaceConfig | None = None,
    state: WorkspaceState | None = None,
    workspace_dir: Path | None = None,
) -> InstallerStatusResult:
    """Query AWS and return installer status data (read-only)."""
    if config is not None and workspace_dir is not None:
        resolved_workspace_dir = workspace_dir
        resolved_config = config
        resolved_state = state
    else:
        ctx = load_workspace_context(
            target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED
        )
        resolved_workspace_dir = ctx.workspace_dir
        resolved_config = ctx.config
        resolved_state = ctx.state

    aws_context = resolve_aws_execution_context(
        profile=resolved_config.aws.profile,
        region=resolved_config.aws.region,
        role_arn=resolved_config.aws.role_arn,
        expected_account_id=resolved_config.aws.account_id,
        prime_credentials=resolved_config.aws.prime_credentials,
    )
    cfn_stack_name = resolved_config.installer.stack_name or "AWSAccelerator-InstallerStack"
    cfn_client = (
        aws_context.factory.get_client("cloudformation") if aws_context.identity else None
    )
    cfn_status = get_cloudformation_stack_status(client=cfn_client, stack_name=cfn_stack_name)

    prefix = resolved_config.lza.accelerator_prefix or "AWSAccelerator"
    installer_pipeline_name = (
        resolved_config.pipelines.installer.name or f"{prefix}-Installer"
    )
    codepipeline_client = (
        aws_context.factory.get_client("codepipeline") if aws_context.identity else None
    )
    pipeline_state = get_pipeline_state(
        client=codepipeline_client, pipeline_name=installer_pipeline_name
    )

    return prepare_installer_status(
        workspace_dir=resolved_workspace_dir,
        config=resolved_config,
        state=resolved_state,
        profile=resolved_config.aws.profile or "",
        region=aws_context.region,
        aws_identity=aws_context.identity,
        aws_error=aws_context.error,
        cfn_status=cfn_status,
        pipeline_state=pipeline_state,
    )


__all__ = [
    "InstallerStatusResult",
    "get_installer_status_workflow",
    "normalize_lza_version",
    "prepare_installer_status",
]
