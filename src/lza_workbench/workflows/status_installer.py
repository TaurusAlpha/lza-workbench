"""Workflow for querying installer stack status."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lza_workbench.aws.cloudformation import (
    CfnStackStatusResult,
    get_cloudformation_stack_status,
)
from lza_workbench.aws.codepipeline import PipelineStateResult, get_pipeline_state
from lza_workbench.aws.context import AwsExecutionContext, resolve_aws_execution_context
from lza_workbench.installer.deployed_version import resolve_deployed_installer_version
from lza_workbench.installer.status import (
    StateAlignment,
    calculate_configuration_drift,
    calculate_state_alignment,
)
from lza_workbench.installer.versions import normalize_lza_version
from lza_workbench.workspace.context import WorkspaceCapability, load_workspace_context
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
    deployed_version: str,
    pipeline_state: PipelineStateResult | None = None,
) -> InstallerStatusResult:
    """Prepare report data without calling AWS, writing files, or rendering output."""
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


def _query_live_installer_status(
    *,
    aws_context: AwsExecutionContext,
    cfn_stack_name: str,
    installer_pipeline_name: str,
    accelerator_prefix: str,
    resolved_config_version: str,
    resolved_state: WorkspaceState | None,
) -> tuple[CfnStackStatusResult, str | None, PipelineStateResult]:
    cfn_client = aws_context.factory.get_client("cloudformation")
    cfn_status = get_cloudformation_stack_status(client=cfn_client, stack_name=cfn_stack_name)
    ssm_client = aws_context.factory.get_client("ssm") if cfn_status.exists else None
    deployed_version = (
        resolve_deployed_installer_version(
            cfn_client=cfn_client,
            ssm_client=ssm_client,
            stack_name=cfn_stack_name,
            accelerator_prefix=(
                cfn_status.deployed_parameters.get("AcceleratorPrefix")
                or accelerator_prefix
            ),
        )
        if cfn_status.exists
        else None
    )
    codepipeline_client = aws_context.factory.get_client("codepipeline")
    pipeline_state = get_pipeline_state(
        client=codepipeline_client, pipeline_name=installer_pipeline_name
    )

    # If a connection/network failure occurred during live execution, fall back to recorded state
    if (
        isinstance(cfn_status.error, str)
        and cfn_status.error.startswith("Connection failure")
        and resolved_state
    ):
        recorded_status = resolved_state.installer_stack_status
        if recorded_status:
            cfn_status = CfnStackStatusResult(
                stack_name=cfn_stack_name,
                exists=True,
                stack_status=recorded_status,
                error=cfn_status.error,
            )
        if not deployed_version and resolved_state.installer_template_version:
            deployed_version = resolved_state.installer_template_version
    if (
        isinstance(pipeline_state.error, str)
        and pipeline_state.error.startswith("Connection failure")
        and resolved_state
    ):
        pipeline_state = PipelineStateResult(
            pipeline_name=installer_pipeline_name,
            exists=bool(resolved_state.installer_pipeline_status),
            status=resolved_state.installer_pipeline_status or "NOT_CHECKED",
            latest_execution_id=resolved_state.installer_pipeline_execution_id,
            error=pipeline_state.error,
        )
    return cfn_status, deployed_version, pipeline_state


def _query_recorded_installer_status(
    *,
    cfn_stack_name: str,
    installer_pipeline_name: str,
    aws_error: str | None,
    resolved_config_version: str,
    resolved_state: WorkspaceState | None,
) -> tuple[CfnStackStatusResult, str, PipelineStateResult]:
    recorded_status = resolved_state.installer_stack_status if resolved_state else None
    recorded_version = resolved_state.installer_template_version if resolved_state else None
    cfn_status = CfnStackStatusResult(
        stack_name=cfn_stack_name,
        exists=bool(recorded_status),
        stack_status=recorded_status,
        error=aws_error,
    )
    deployed_version = recorded_version or resolved_config_version
    recorded_pipe_status = (
        resolved_state.installer_pipeline_status if resolved_state else None
    )
    recorded_exec_id = (
        resolved_state.installer_pipeline_execution_id if resolved_state else None
    )
    pipeline_state = PipelineStateResult(
        pipeline_name=installer_pipeline_name,
        exists=bool(recorded_pipe_status),
        status=recorded_pipe_status or "NOT_CHECKED",
        latest_execution_id=recorded_exec_id,
    )
    return cfn_status, deployed_version, pipeline_state


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
            target_dir, required_capabilities=(WorkspaceCapability.METADATA_VALID,)
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
    prefix = resolved_config.lza.accelerator_prefix or "AWSAccelerator"
    installer_pipeline_name = (
        resolved_config.pipelines.installer.name or f"{prefix}-Installer"
    )

    if aws_context.is_live:
        cfn_status, deployed_version, pipeline_state = _query_live_installer_status(
            aws_context=aws_context,
            cfn_stack_name=cfn_stack_name,
            installer_pipeline_name=installer_pipeline_name,
            accelerator_prefix=prefix,
            resolved_config_version=resolved_config.lza.version,
            resolved_state=resolved_state,
        )
    else:
        cfn_status, deployed_version, pipeline_state = _query_recorded_installer_status(
            cfn_stack_name=cfn_stack_name,
            installer_pipeline_name=installer_pipeline_name,
            aws_error=aws_context.error,
            resolved_config_version=resolved_config.lza.version,
            resolved_state=resolved_state,
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
        deployed_version=deployed_version or resolved_config.lza.version,
        pipeline_state=pipeline_state,
    )



__all__ = [
    "InstallerStatusResult",
    "get_installer_status_workflow",
    "normalize_lza_version",
    "prepare_installer_status",
]
