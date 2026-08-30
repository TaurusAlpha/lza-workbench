"""Workflow for querying and synchronizing installer stack status."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
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
from lza_workbench.installer.parameters import apply_deployed_installer_parameters
from lza_workbench.installer.status import (
    StateAlignment,
    calculate_configuration_drift,
    calculate_state_alignment,
)
from lza_workbench.installer.versions import branch_to_version, normalize_lza_version
from lza_workbench.workspace.config import write_workspace_config
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context
from lza_workbench.workspace.schema import WorkspaceConfig, WorkspaceState
from lza_workbench.workspace.state import write_workspace_state


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
    state_synced: bool = False
    config_synced: bool = False


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
    state_synced: bool = False,
    config_synced: bool = False,
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
        state_synced=state_synced,
        config_synced=config_synced,
    )


def sync_installer_state(
    *,
    workspace_dir: Path,
    state: WorkspaceState,
    cfn_status: CfnStackStatusResult,
    deployed_version: str,
) -> WorkspaceState:
    """Synchronize .lza/state.json deployment metadata with live installer state."""
    if not cfn_status.exists:
        raise LzaError(
            "Cannot synchronize state: CloudFormation installer stack is not deployed "
            "or inaccessible."
        )
    state.installer_stack_id = cfn_status.stack_id
    state.installer_stack_status = cfn_status.stack_status
    state.installer_template_version = deployed_version
    state.updated_at = datetime.now(UTC)
    write_workspace_state(workspace_dir, state)
    return state


def sync_installer_config(
    *, workspace_dir: Path, config: WorkspaceConfig, cfn_status: CfnStackStatusResult
) -> WorkspaceConfig:
    """Synchronize lza-workspace.yaml with deployed installer parameters."""
    if not cfn_status.exists or not cfn_status.deployed_parameters:
        raise LzaError(
            "Cannot synchronize config: CloudFormation installer stack is not deployed "
            "or has no parameters."
        )
    apply_deployed_installer_parameters(
        config,
        cfn_status.deployed_parameters,
        stack_id=cfn_status.stack_id,
    )
    write_workspace_config(workspace_dir, config)
    return config


def get_installer_status_workflow(
    *,
    sync_state: bool = False,
    sync_config: bool = False,
    target_dir: Path | None = None,
    config: WorkspaceConfig | None = None,
    state: WorkspaceState | None = None,
    workspace_dir: Path | None = None,
) -> InstallerStatusResult:
    """Query AWS, optionally synchronize, and return installer status data."""
    if sync_config:
        sync_state = True

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
    cfn_client = aws_context.factory.get_client("cloudformation") if aws_context.identity else None
    cfn_status = get_cloudformation_stack_status(client=cfn_client, stack_name=cfn_stack_name)
    deployed_version = branch_to_version(
        cfn_status.deployed_parameters.get("RepositoryBranchName", "") if cfn_status.exists else ""
    )

    prefix = resolved_config.lza.accelerator_prefix or "AWSAccelerator"
    installer_pipeline_name = resolved_config.pipelines.installer.name or f"{prefix}-Installer"
    codepipeline_client = (
        aws_context.factory.get_client("codepipeline") if aws_context.identity else None
    )
    pipeline_state = get_pipeline_state(
        client=codepipeline_client, pipeline_name=installer_pipeline_name
    )

    state_synced = False
    config_synced = False

    if sync_state and cfn_status.exists:
        resolved_state = sync_installer_state(
            workspace_dir=resolved_workspace_dir,
            state=resolved_state or WorkspaceState.from_config(resolved_config),
            cfn_status=cfn_status,
            deployed_version=deployed_version,
        )
        state_synced = True

    if sync_config and cfn_status.exists and cfn_status.deployed_parameters:
        resolved_config = sync_installer_config(
            workspace_dir=resolved_workspace_dir,
            config=resolved_config,
            cfn_status=cfn_status,
        )
        config_synced = True

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
        state_synced=state_synced,
        config_synced=config_synced,
    )


__all__ = [
    "InstallerStatusResult",
    "get_installer_status_workflow",
    "normalize_lza_version",
    "prepare_installer_status",
    "sync_installer_config",
    "sync_installer_state",
]
