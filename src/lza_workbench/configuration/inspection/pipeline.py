"""Remote configuration CodePipeline inspection and failure diagnostics."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lza_workbench.configuration.inspection.models import ConfigurationPipelineStatus
from lza_workbench.infrastructure.aws.codepipeline import PipelineStateResult, get_pipeline_state
from lza_workbench.pipeline.failures import (
    collect_pipeline_action_failures,
    fetch_codebuild_diagnostics,
)

if TYPE_CHECKING:
    from lza_workbench.workspace.schema import WorkspaceConfig, WorkspaceState


def inspect_configuration_pipeline(
    *,
    resolved_config: WorkspaceConfig,
    resolved_state: WorkspaceState | None,
    aws_identity: dict[str, Any] | None,
    region: str,
    account_id: str,
    factory: Any,
) -> ConfigurationPipelineStatus:
    """Query live CodePipeline state or fall back to recorded execution state."""
    prefix = resolved_config.lza.accelerator_prefix or "AWSAccelerator"
    config_pipeline_name = resolved_config.pipelines.configuration.name or f"{prefix}-Pipeline"
    config_pipeline_arn = f"arn:aws:codepipeline:{region}:{account_id}:{config_pipeline_name}"

    pipeline_status: str | None = None
    pipeline_execution_id: str | None = None
    pipeline_failed_stage: str | None = None
    pipeline_failed_action: str | None = None
    pipeline_failed_build_url: str | None = None
    pipeline_error: str | None = None
    pipeline_state: PipelineStateResult | None = None

    if aws_identity:
        codepipeline_client = factory.get_client("codepipeline")
        pipeline_state = get_pipeline_state(
            client=codepipeline_client, pipeline_name=config_pipeline_name
        )
        if pipeline_state.exists and pipeline_state.status != "NOT_CHECKED":
            pipeline_status = pipeline_state.status
            pipeline_execution_id = pipeline_state.latest_execution_id
            if pipeline_state.status in {"Failed", "Cancelled"}:
                codebuild_client = factory.get_client("codebuild")
                logs_client = factory.get_client("logs")
                failures = collect_pipeline_action_failures(
                    pipeline_state.stages,
                    fetch_diagnostics=lambda build_id: fetch_codebuild_diagnostics(
                        codebuild_client=codebuild_client,
                        logs_client=logs_client,
                        build_id=build_id,
                    ),
                )
                if failures:
                    failure = failures[0]
                    pipeline_failed_stage = failure.stage_name
                    pipeline_failed_action = failure.action_name
                    pipeline_failed_build_url = failure.external_execution_url
                    pipeline_error = "\n".join(failure.diagnostic_details) or (
                        failure.error_message or failure.summary
                    )
    elif resolved_state and resolved_state.config_pipeline_status:
        pipeline_status = resolved_state.config_pipeline_status
        pipeline_execution_id = resolved_state.config_pipeline_execution_id
        pipeline_failed_stage = resolved_state.config_pipeline_failed_stage
        pipeline_failed_action = resolved_state.config_pipeline_failed_action
        pipeline_failed_build_url = resolved_state.config_pipeline_failed_build_url
        pipeline_error = resolved_state.config_pipeline_error

    return ConfigurationPipelineStatus(
        name=config_pipeline_name,
        arn=config_pipeline_arn,
        status=pipeline_status,
        execution_id=pipeline_execution_id,
        failed_stage=pipeline_failed_stage,
        failed_action=pipeline_failed_action,
        failed_build_url=pipeline_failed_build_url,
        error=pipeline_error,
        state=pipeline_state,
    )


__all__ = [
    "inspect_configuration_pipeline",
]
