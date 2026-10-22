"""Remote configuration CodePipeline inspection and failure diagnostics."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lza_workbench.configuration.inspection.models import ConfigurationPipelineStatus
from lza_workbench.pipeline.observation import observe_pipeline_status

if TYPE_CHECKING:
    from lza_workbench.workspace.schema import (
        CustomerEnvironmentTarget,
        WorkspaceConfig,
        WorkspaceState,
    )


def inspect_configuration_pipeline(
    *,
    aws_identity: dict[str, Any] | None,
    region: str,
    account_id: str,
    factory: Any,
    environment_target: CustomerEnvironmentTarget | None = None,
    resolved_config: WorkspaceConfig | None = None,
    resolved_state: WorkspaceState | None = None,
    pipeline_name: str | None = None,
    accelerator_prefix: str = "AWSAccelerator",
) -> ConfigurationPipelineStatus:
    """Query live CodePipeline state or fall back to recorded execution state."""
    env_target = environment_target or (
        resolved_config.environment_target if resolved_config is not None else None
    )
    prefix = (
        (env_target.lza.accelerator_prefix if env_target is not None else accelerator_prefix)
        or "AWSAccelerator"
    )
    config_pipeline_name = (
        pipeline_name
        or (env_target.configuration_pipeline_name if env_target is not None else None)
        or f"{prefix}-Pipeline"
    )
    config_pipeline_arn = f"arn:aws:codepipeline:{region}:{account_id}:{config_pipeline_name}"

    summary = observe_pipeline_status(
        pipeline_name=config_pipeline_name,
        pipeline_type="configuration",
        factory=factory if aws_identity else None,
        state=resolved_state,
        fetch_diagnostics=True,
    )

    return ConfigurationPipelineStatus(
        name=config_pipeline_name,
        arn=config_pipeline_arn,
        status=summary.status,
        execution_id=summary.execution_id,
        failed_stage=summary.failed_stage,
        failed_action=summary.failed_action,
        failed_build_url=summary.failed_build_url,
        failure_summary=summary.failure_summary,
        error=summary.error,
        state=summary.raw_state,
        is_live=summary.is_live,
        outcome=summary.outcome,
        observed_at=summary.observed_at,
    )


__all__ = [
    "inspect_configuration_pipeline",
]
