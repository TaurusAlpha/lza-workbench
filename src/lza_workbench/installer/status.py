"""Installer stack status query, calculations, and reporting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from lza_workbench.infrastructure.aws.cloudformation import (
    CfnStackStatusResult,
    get_cloudformation_stack_status,
)
from lza_workbench.infrastructure.aws.codepipeline import (
    PipelineStateResult,
)
from lza_workbench.infrastructure.aws.errors import (
    ObservationOutcome,
    outcome_from_aws_error,
)
from lza_workbench.infrastructure.aws.session import (
    AwsExecutionContext,
    resolve_aws_execution_context,
)
from lza_workbench.installer.drift import (
    StateAlignment,
    calculate_configuration_drift,
    calculate_state_alignment,
    compare_installer_parameters,
)
from lza_workbench.installer.schema import LzaInstaller
from lza_workbench.installer.versions import (
    normalize_lza_version,
    resolve_deployed_installer_version,
)
from lza_workbench.pipeline.observation import observe_pipeline_status
from lza_workbench.workspace.context import load_workspace_context
from lza_workbench.workspace.schema import (
    CustomerEnvironmentTarget,
    WorkspaceConfig,
    WorkspaceState,
)
from lza_workbench.workspace.validation import WorkspaceCapability

if TYPE_CHECKING:
    from lza_workbench.infrastructure.aws.session import AwsClientFactory


@dataclass(frozen=True)
class InstallerStackSummary:
    name: str
    status: str | None = None
    exists: bool = False
    deployed_version: str | None = None
    is_live: bool = True
    outcome: ObservationOutcome = ObservationOutcome.NOT_COLLECTED
    observed_at: datetime | None = None
    last_attempt_at: datetime | None = None
    error: str | None = None
    stack_id: str | None = None
    resource_updated_at: str | None = None


@dataclass(frozen=True)
class InstallerStatusResult:
    workspace_dir: Path | None
    config: WorkspaceConfig | None
    state: WorkspaceState | None
    profile: str
    region: str
    aws_identity: dict[str, str] | None
    aws_error: str | None
    cfn_status: CfnStackStatusResult
    deployed_version: str | None
    configuration_drift: dict[str, tuple[str, str]]
    state_alignment: StateAlignment | None
    installer_pipeline_name: str
    pipeline_state: PipelineStateResult | None = None
    parameter_comparison: str = "Not checked"
    environment_target: CustomerEnvironmentTarget | None = None
    installer: LzaInstaller | None = None

    def __post_init__(self) -> None:
        if self.environment_target is None and self.config is not None:
            object.__setattr__(self, "environment_target", self.config.environment_target)
        if self.installer is None and self.config is not None:
            object.__setattr__(self, "installer", self.config.installer)


def prepare_installer_status(
    *,
    workspace_dir: Path | None,
    config: WorkspaceConfig | None = None,
    environment_target: CustomerEnvironmentTarget | None = None,
    installer: LzaInstaller | None = None,
    state: WorkspaceState | None,
    profile: str,
    region: str,
    aws_identity: dict[str, str] | None,
    aws_error: str | None,
    cfn_status: CfnStackStatusResult,
    deployed_version: str | None,
    pipeline_state: PipelineStateResult | None = None,
) -> InstallerStatusResult:
    """Prepare report data without calling AWS, writing files, or rendering output."""
    resolved_target = environment_target or (
        config.environment_target if config is not None else None
    )
    resolved_installer = installer or (config.installer if config is not None else None)
    if resolved_target is None:
        raise ValueError("prepare_installer_status requires environment_target or config.")

    drift = (
        calculate_configuration_drift(
            config,
            cfn_status.deployed_parameters,
            installer=resolved_installer,
            environment_target=resolved_target,
        )
        if resolved_installer is not None and cfn_status.exists and cfn_status.deployed_parameters
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
    parameter_comparison = "Not checked"
    if aws_identity is not None and not cfn_status.error:
        if not cfn_status.exists:
            parameter_comparison = "Not deployed"
        elif cfn_status.deployed_parameters and resolved_installer is not None:
            obs = state.installer.observation if state else None
            baseline = obs.deployed_parameters if (obs and obs.deployed_parameters) else None
            if obs and obs.stack_id and obs.stack_id != cfn_status.stack_id:
                baseline = None
            parameter_comparison = compare_installer_parameters(
                config,
                cfn_status.deployed_parameters,
                baseline,
                installer=resolved_installer,
                environment_target=resolved_target,
            )
    installer_pipeline_name = resolved_target.installer_pipeline_name
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
        parameter_comparison=parameter_comparison,
        environment_target=resolved_target,
        installer=resolved_installer,
    )


def observe_installer_stack(
    *,
    target: CustomerEnvironmentTarget,
    factory: AwsClientFactory | None = None,
    state: WorkspaceState | None = None,
) -> InstallerStackSummary:
    """Collect unified installer stack observation with CloudFormation query and offline fallback."""
    now = datetime.now(UTC)
    cfn_stack_name = target.installer_stack_name or "AWSAccelerator-InstallerStack"

    if factory is not None:
        cfn_client = factory.get_client("cloudformation")
        cfn_status = get_cloudformation_stack_status(client=cfn_client, stack_name=cfn_stack_name)
        if cfn_status.error:
            outcome = (
                outcome_from_aws_error(cfn_status.error_info)
                if cfn_status.error_info is not None
                else ObservationOutcome.COLLECTION_FAILED
            )
            is_not_found = (
                cfn_status.error_info.is_not_found
                if cfn_status.error_info is not None
                else False
            )
            if is_not_found or cfn_status.stack_status == "NOT_DEPLOYED":
                return InstallerStackSummary(
                    name=cfn_stack_name,
                    status="NOT_DEPLOYED",
                    exists=False,
                    deployed_version=None,
                    is_live=True,
                    outcome=ObservationOutcome.ABSENT,
                    observed_at=now,
                    last_attempt_at=now,
                )
            # Live query failed: preserve last-known observation while recording failure attempt
            obs = state.installer.observation if state else None
            if obs and obs.stack_status:
                return InstallerStackSummary(
                    name=cfn_stack_name,
                    status=obs.stack_status,
                    exists=bool(obs.stack_status),
                    deployed_version=obs.deployed_version,
                    is_live=False,
                    outcome=outcome,
                    observed_at=obs.observed_at,
                    last_attempt_at=now,
                    error=cfn_status.error,
                    stack_id=obs.stack_id,
                )
            return InstallerStackSummary(
                name=cfn_stack_name,
                status=None,
                exists=False,
                deployed_version=None,
                is_live=False,
                outcome=outcome,
                observed_at=None,
                last_attempt_at=now,
                error=cfn_status.error,
            )

        if not cfn_status.exists:
            return InstallerStackSummary(
                name=cfn_stack_name,
                status="NOT_DEPLOYED",
                exists=False,
                deployed_version=None,
                is_live=True,
                outcome=ObservationOutcome.ABSENT,
                observed_at=now,
                last_attempt_at=now,
            )

        ssm_client = factory.get_client("ssm")
        deployed_version = resolve_deployed_installer_version(
            cfn_client=cfn_client,
            ssm_client=ssm_client,
            stack_name=cfn_stack_name,
            accelerator_prefix=(
                cfn_status.deployed_parameters.get("AcceleratorPrefix")
                or target.lza.accelerator_prefix
            ),
        )

        return InstallerStackSummary(
            name=cfn_stack_name,
            status=cfn_status.stack_status,
            exists=True,
            deployed_version=deployed_version,
            is_live=True,
            outcome=ObservationOutcome.OBSERVED,
            observed_at=now,
            last_attempt_at=now,
            stack_id=cfn_status.stack_id,
            resource_updated_at=cfn_status.last_updated_time or cfn_status.creation_time,
        )

    # Offline / No factory
    obs = state.installer.observation if state else None
    if obs and obs.stack_status:
        return InstallerStackSummary(
            name=cfn_stack_name,
            status=obs.stack_status,
            exists=bool(obs.stack_status),
            deployed_version=obs.deployed_version,
            is_live=False,
            outcome=ObservationOutcome.NOT_COLLECTED,
            observed_at=obs.observed_at,
            last_attempt_at=None,
            stack_id=obs.stack_id,
        )

    return InstallerStackSummary(
        name=cfn_stack_name,
        status=None,
        exists=False,
        deployed_version=None,
        is_live=False,
        outcome=ObservationOutcome.NOT_COLLECTED,
    )


def _query_live_installer_status(
    *,
    aws_context: AwsExecutionContext,
    cfn_stack_name: str,
    installer_pipeline_name: str,
    accelerator_prefix: str,
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
                cfn_status.deployed_parameters.get("AcceleratorPrefix") or accelerator_prefix
            ),
        )
        if cfn_status.exists
        else None
    )

    pipe_summary = observe_pipeline_status(
        pipeline_name=installer_pipeline_name,
        pipeline_type="installer",
        factory=aws_context.factory,
        state=resolved_state,
        fetch_diagnostics=False,
    )
    pipeline_state = pipe_summary.raw_state or PipelineStateResult(
        pipeline_name=installer_pipeline_name,
        exists=pipe_summary.exists,
        status=pipe_summary.status or "NOT_CHECKED",
        latest_execution_id=pipe_summary.execution_id,
        latest_start_time=pipe_summary.start_time,
        error=pipe_summary.error,
        error_info=getattr(pipe_summary.raw_state, "error_info", None) if pipe_summary.raw_state else None,
    )

    # If live CloudFormation query failed, fall back to recorded state without inventing data
    if cfn_status.error and resolved_state:
        obs = resolved_state.installer.observation
        recorded_status = obs.stack_status if obs else None
        if recorded_status:
            cfn_status = CfnStackStatusResult(
                stack_name=cfn_stack_name,
                exists=True,
                stack_id=obs.stack_id if obs else None,
                stack_status=recorded_status,
                deployed_parameters=dict(obs.deployed_parameters) if (obs and obs.deployed_parameters) else {},
                error=cfn_status.error,
                error_info=cfn_status.error_info,
            )
        recorded_version = obs.deployed_version if obs else None
        if not deployed_version and recorded_version:
            deployed_version = recorded_version

    return cfn_status, deployed_version, pipeline_state


def _query_recorded_installer_status(
    *,
    cfn_stack_name: str,
    installer_pipeline_name: str,
    aws_error: str | None,
    resolved_state: WorkspaceState | None,
) -> tuple[CfnStackStatusResult, str | None, PipelineStateResult]:
    obs = resolved_state.installer.observation if resolved_state else None
    recorded_status = obs.stack_status if obs else None
    recorded_version = obs.deployed_version if obs else None
    cfn_status = CfnStackStatusResult(
        stack_name=cfn_stack_name,
        exists=bool(recorded_status),
        stack_id=obs.stack_id if obs else None,
        stack_status=recorded_status,
        deployed_parameters=dict(obs.deployed_parameters) if (obs and obs.deployed_parameters) else {},
        error=aws_error,
    )
    pipe_summary = observe_pipeline_status(
        pipeline_name=installer_pipeline_name,
        pipeline_type="installer",
        factory=None,
        state=resolved_state,
        fetch_diagnostics=False,
    )
    pipeline_state = PipelineStateResult(
        pipeline_name=installer_pipeline_name,
        exists=pipe_summary.exists,
        status=pipe_summary.status or "NOT_CHECKED",
        latest_execution_id=pipe_summary.execution_id,
        latest_start_time=pipe_summary.start_time,
        error=pipe_summary.error,
    )
    return cfn_status, recorded_version, pipeline_state


def get_installer_status_workflow(
    *,
    target_dir: Path | None = None,
    environment_target: CustomerEnvironmentTarget | None = None,
    installer: LzaInstaller | None = None,
    config: WorkspaceConfig | None = None,
    state: WorkspaceState | None = None,
    workspace_dir: Path | None = None,
    aws_context: AwsExecutionContext | None = None,
) -> InstallerStatusResult:
    if environment_target is not None:
        resolved_workspace_dir = workspace_dir
        resolved_config = config
        resolved_target = environment_target
        resolved_installer = installer or (config.installer if config is not None else None)
        resolved_state = state
    elif config is not None:
        resolved_workspace_dir = workspace_dir
        resolved_config = config
        resolved_target = config.environment_target
        resolved_installer = installer or config.installer
        resolved_state = state
    else:
        ctx = load_workspace_context(
            target_dir, required_capabilities=(WorkspaceCapability.METADATA_VALID,)
        )
        resolved_workspace_dir = ctx.workspace_dir
        resolved_config = ctx.config
        resolved_target = ctx.config.environment_target
        resolved_installer = installer or ctx.config.installer
        resolved_state = ctx.state

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
    cfn_stack_name = resolved_target.installer_stack_name or "AWSAccelerator-InstallerStack"
    prefix = resolved_target.lza.accelerator_prefix
    installer_pipeline_name = resolved_target.installer_pipeline_name

    if resolved_aws.is_live:
        cfn_status, deployed_version, pipeline_state = _query_live_installer_status(
            aws_context=resolved_aws,
            cfn_stack_name=cfn_stack_name,
            installer_pipeline_name=installer_pipeline_name,
            accelerator_prefix=prefix,
            resolved_state=resolved_state,
        )
    else:
        cfn_status, deployed_version, pipeline_state = _query_recorded_installer_status(
            cfn_stack_name=cfn_stack_name,
            installer_pipeline_name=installer_pipeline_name,
            aws_error=resolved_aws.error,
            resolved_state=resolved_state,
        )

    return prepare_installer_status(
        workspace_dir=resolved_workspace_dir,
        config=resolved_config,
        environment_target=resolved_target,
        installer=resolved_installer,
        state=resolved_state,
        profile=profile or "",
        region=resolved_aws.region,
        aws_identity=resolved_aws.identity,
        aws_error=resolved_aws.error,
        cfn_status=cfn_status,
        deployed_version=deployed_version,
        pipeline_state=pipeline_state,
    )


__all__ = [
    "InstallerStackSummary",
    "InstallerStatusResult",
    "StateAlignment",
    "calculate_configuration_drift",
    "calculate_state_alignment",
    "get_installer_status_workflow",
    "normalize_lza_version",
    "observe_installer_stack",
    "prepare_installer_status",
]
