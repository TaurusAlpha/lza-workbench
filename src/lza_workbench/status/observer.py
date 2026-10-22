"""Workflow for gathering root workspace status data."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lza_workbench.configuration.status import (
    ConfigurationRepoSummary,
    observe_configuration_repository,
)
from lza_workbench.infrastructure.aws.errors import ObservationOutcome
from lza_workbench.infrastructure.aws.session import (
    AwsExecutionContext,
    resolve_aws_execution_context,
)
from lza_workbench.installer.state import (
    record_installer_attempt,
    record_installer_observation,
)
from lza_workbench.installer.status import (
    InstallerStackSummary,
    observe_installer_stack,
)
from lza_workbench.pipeline.observation import observe_pipeline_status
from lza_workbench.pipeline.resolution import resolve_pipeline
from lza_workbench.pipeline.state import (
    record_pipeline_attempt,
    record_pipeline_observation,
)
from lza_workbench.status.health import (
    derive_overall_health,
)
from lza_workbench.status.summary import (
    OverallHealthSummary,
    PipelineSummary,
    RootStatusResult,
)
from lza_workbench.workspace.context import load_workspace_context
from lza_workbench.workspace.persistence import (
    get_state_path,
    load_workspace_state,
    update_workspace_state,
)
from lza_workbench.workspace.schema import (
    CustomerEnvironmentTarget,
    WorkspaceConfig,
    WorkspaceState,
)
from lza_workbench.workspace.validation import (
    WorkspaceAssessment,
    WorkspaceCapability,
    evaluate_workspace_assessment,
)

# Retained alias for test compatibility
_derive_overall_health = derive_overall_health


def _persist_live_observations(
    state: WorkspaceState,
    *,
    installer_stack: InstallerStackSummary,
    installer_pipe: PipelineSummary,
    config_pipe: PipelineSummary,
) -> None:
    now = datetime.now(UTC)
    # Installer stack persistence
    if installer_stack.outcome == ObservationOutcome.OBSERVED:
        record_installer_observation(
            state,
            stack_name=installer_stack.name,
            stack_id=installer_stack.stack_id,
            stack_status=installer_stack.status,
            deployed_version=installer_stack.deployed_version,
            observed_at=installer_stack.observed_at or now,
            last_attempt_at=installer_stack.last_attempt_at or now,
            exists=True,
        )
    elif installer_stack.outcome == ObservationOutcome.ABSENT:
        record_installer_observation(
            state,
            stack_name=installer_stack.name,
            stack_id=None,
            stack_status="NOT_DEPLOYED",
            deployed_version=None,
            deployed_parameters={},
            observed_at=installer_stack.observed_at or now,
            last_attempt_at=installer_stack.last_attempt_at or now,
            exists=False,
        )
    elif installer_stack.outcome in (
        ObservationOutcome.COLLECTION_FAILED,
        ObservationOutcome.ACCESS_DENIED,
        ObservationOutcome.AUTH_UNAVAILABLE,
    ):
        record_installer_attempt(
            state,
            last_attempt_at=installer_stack.last_attempt_at or now,
            error=installer_stack.error,
        )

    # Installer pipeline persistence
    if installer_pipe.outcome == ObservationOutcome.OBSERVED:
        record_pipeline_observation(
            state,
            pipeline_name=installer_pipe.name,
            execution_id=installer_pipe.execution_id,
            status=installer_pipe.status,
            pipeline_type="installer",
            failed_stage=installer_pipe.failed_stage,
            failed_action=installer_pipe.failed_action,
            failed_build_url=installer_pipe.failed_build_url,
            error=installer_pipe.failure_summary,
            observed_at=installer_pipe.observed_at or now,
            last_attempt_at=installer_pipe.last_attempt_at or now,
            exists=True,
        )
    elif installer_pipe.outcome == ObservationOutcome.ABSENT:
        record_pipeline_observation(
            state,
            pipeline_name=installer_pipe.name,
            execution_id=None,
            status="Not Deployed",
            pipeline_type="installer",
            observed_at=installer_pipe.observed_at or now,
            last_attempt_at=installer_pipe.last_attempt_at or now,
            exists=False,
        )
    elif installer_pipe.outcome in (
        ObservationOutcome.COLLECTION_FAILED,
        ObservationOutcome.ACCESS_DENIED,
        ObservationOutcome.AUTH_UNAVAILABLE,
    ):
        record_pipeline_attempt(
            state,
            pipeline_type="installer",
            last_attempt_at=installer_pipe.last_attempt_at or now,
            error=installer_pipe.error,
        )

    # Configuration pipeline persistence
    if config_pipe.outcome == ObservationOutcome.OBSERVED:
        record_pipeline_observation(
            state,
            pipeline_name=config_pipe.name,
            execution_id=config_pipe.execution_id,
            status=config_pipe.status,
            pipeline_type="configuration",
            failed_stage=config_pipe.failed_stage,
            failed_action=config_pipe.failed_action,
            failed_build_url=config_pipe.failed_build_url,
            error=config_pipe.failure_summary,
            observed_at=config_pipe.observed_at or now,
            last_attempt_at=config_pipe.last_attempt_at or now,
            exists=True,
        )
    elif config_pipe.outcome == ObservationOutcome.ABSENT:
        record_pipeline_observation(
            state,
            pipeline_name=config_pipe.name,
            execution_id=None,
            status="Not Deployed",
            pipeline_type="configuration",
            observed_at=config_pipe.observed_at or now,
            last_attempt_at=config_pipe.last_attempt_at or now,
            exists=False,
        )
    elif config_pipe.outcome in (
        ObservationOutcome.COLLECTION_FAILED,
        ObservationOutcome.ACCESS_DENIED,
        ObservationOutcome.AUTH_UNAVAILABLE,
    ):
        record_pipeline_attempt(
            state,
            pipeline_type="configuration",
            last_attempt_at=config_pipe.last_attempt_at or now,
            error=config_pipe.error,
        )


def get_root_status_workflow(
    *,
    target_dir: Path | None = None,
    environment_target: CustomerEnvironmentTarget | None = None,
    config: WorkspaceConfig | None = None,
    aws_context: AwsExecutionContext | None = None,
    state: WorkspaceState | None = None,
    workspace_dir: Path | None = None,
    config_dir: Path | None = None,
) -> RootStatusResult:
    """Compose root summary status from feature-owned observation collectors."""
    assessment: WorkspaceAssessment | None = None
    resolved_config_dir: Path | None = config_dir

    if config is None and environment_target is None:
        ctx = load_workspace_context(
            target_dir,
            required_capabilities=(WorkspaceCapability.METADATA_VALID,),
            include_state=False,
        )
        workspace_dir, config = ctx.workspace_dir, ctx.config
        state = ctx.state if ctx.state != WorkspaceState() else None
        assessment = ctx.assessment
        if resolved_config_dir is None:
            resolved_config_dir = (
                ctx.config_dir
                if isinstance(getattr(ctx, "config_dir", None), Path)
                else (workspace_dir / config.configuration.local_path)
            )
    else:
        workspace_dir = workspace_dir or target_dir
        if workspace_dir is not None and config is not None:
            if resolved_config_dir is None:
                resolved_config_dir = workspace_dir / config.configuration.local_path
            assessment = evaluate_workspace_assessment(workspace_dir, config)

    resolved_target = environment_target or (
        config.environment_target if config is not None else None
    )
    assert resolved_target is not None

    profile = (
        (config.aws.profile or "")
        if config is not None
        else (aws_context.factory.profile or "" if aws_context is not None else "")
    )
    if aws_context is None:
        if config is not None:
            aws_context = resolve_aws_execution_context(
                profile=profile,
                region=config.aws.region,
                role_arn=config.aws.role_arn,
                expected_account_id=config.aws.account_id,
                prime_credentials=config.aws.prime_credentials,
            )
        else:
            aws_context = resolve_aws_execution_context(
                region=resolved_target.region,
                expected_account_id=resolved_target.account_id,
            )

    factory = aws_context.factory
    region = aws_context.region
    aws_identity = aws_context.identity
    aws_error = aws_context.error
    is_live = aws_identity is not None

    if (
        state is None
        and workspace_dir is not None
        and get_state_path(workspace_dir).exists()
    ):
        state = load_workspace_state(workspace_dir)

    # 1. Installer Stack
    installer_stack_summary = observe_installer_stack(
        target=resolved_target,
        factory=factory if is_live else None,
        state=state,
    )

    # 2. Installer Pipeline
    installer_pipeline_name = resolve_pipeline(resolved_target, pipeline_type="installer").name
    installer_pipe_summary = observe_pipeline_status(
        pipeline_name=installer_pipeline_name,
        pipeline_type="installer",
        factory=factory if is_live else None,
        state=state,
    )

    # 3. Configuration Repository & Local Git
    config_repo_summary = observe_configuration_repository(
        target=resolved_target,
        factory=factory if is_live else None,
        config_dir=resolved_config_dir,
        resolved_config=config,
        state=state,
        aws_identity=aws_identity,
        region=region,
    )

    # 4. Configuration Pipeline
    config_pipeline_name = resolve_pipeline(resolved_target, pipeline_type="configuration").name
    config_pipe_summary = observe_pipeline_status(
        pipeline_name=config_pipeline_name,
        pipeline_type="configuration",
        factory=factory if is_live else None,
        state=state,
    )

    # Persist verified live observations to local state when available
    if (
        is_live
        and workspace_dir is not None
        and get_state_path(workspace_dir).exists()
    ):
        try:
            update_workspace_state(
                workspace_dir,
                lambda curr: _persist_live_observations(
                    curr,
                    installer_stack=installer_stack_summary,
                    installer_pipe=installer_pipe_summary,
                    config_pipe=config_pipe_summary,
                ),
            )
        except Exception:
            pass

    # Overall Health Summary
    health = derive_overall_health(
        is_live=is_live,
        installer_stack=installer_stack_summary,
        installer_pipe=installer_pipe_summary,
        config_repo=config_repo_summary,
        config_pipe=config_pipe_summary,
        assessment=assessment,
    )

    now = datetime.now(UTC)
    observed_at = now if is_live else None
    last_attempt_at = now if aws_context is not None else None

    return RootStatusResult(
        workspace_dir=workspace_dir,
        customer_name=resolved_target.customer.name,
        lza_version=resolved_target.lza.version,
        profile=profile,
        region=region,
        aws_identity=aws_identity,
        aws_error=aws_error,
        installer=installer_stack_summary,
        installer_pipeline=installer_pipe_summary,
        configuration_repo=config_repo_summary,
        configuration_pipeline=config_pipe_summary,
        health=health,
        assessment=assessment,
        observed_at=observed_at,
        last_attempt_at=last_attempt_at,
    )


__all__ = [
    "ConfigurationRepoSummary",
    "InstallerStackSummary",
    "OverallHealthSummary",
    "PipelineSummary",
    "RootStatusResult",
    "get_root_status_workflow",
]
