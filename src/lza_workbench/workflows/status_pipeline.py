"""Workflow for gathering pipeline status data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.pipeline.resolution import resolve_pipeline
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context


@dataclass(frozen=True)
class PipelineStatusResult:
    """Prepared pipeline names, ARNs, and execution metadata for rendering."""

    workspace_dir: Path
    customer_name: str
    profile: str
    region: str
    aws_identity: dict[str, str] | None
    aws_error: str | None
    installer_pipeline_name: str
    installer_pipeline_arn: str
    config_pipeline_name: str
    config_pipeline_arn: str
    installer_execution_id: str | None
    config_execution_id: str | None
    has_state: bool


def get_pipeline_status_workflow(
    *,
    target_dir: Path | None = None,
) -> PipelineStatusResult:
    """Query AWS and workspace state for CodePipeline status."""
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED)
    workspace_dir, config, state = ctx.workspace_dir, ctx.config, ctx.state

    profile = config.aws.profile or ""
    aws_context = resolve_aws_execution_context(
        profile=profile,
        region=config.aws.region,
        role_arn=config.aws.role_arn,
        expected_account_id=config.aws.account_id,
    )
    region = aws_context.region
    aws_identity = aws_context.identity
    aws_error = aws_context.error

    account_id = aws_identity["account"] if aws_identity else "UNKNOWN_ACCOUNT"
    installer_pipeline = resolve_pipeline(config, pipeline_type="installer")
    config_pipeline = resolve_pipeline(config, pipeline_type="configuration")

    return PipelineStatusResult(
        workspace_dir=workspace_dir,
        customer_name=config.customer.name,
        profile=profile,
        region=region,
        aws_identity=aws_identity,
        aws_error=aws_error,
        installer_pipeline_name=installer_pipeline.name,
        installer_pipeline_arn=installer_pipeline.arn(region=region, account_id=account_id),
        config_pipeline_name=config_pipeline.name,
        config_pipeline_arn=config_pipeline.arn(region=region, account_id=account_id),
        installer_execution_id=state.installer_pipeline_execution_id if state else None,
        config_execution_id=state.config_pipeline_execution_id if state else None,
        has_state=state is not None,
    )
