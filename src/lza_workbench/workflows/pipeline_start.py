"""Workflow for starting AWS CodePipeline executions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lza_workbench.aws.codepipeline import start_pipeline_execution
from lza_workbench.aws.context import AwsExecutionContext, resolve_aws_execution_context
from lza_workbench.errors import LzaError
from lza_workbench.pipeline.resolution import resolve_pipeline
from lza_workbench.pipeline.state import record_pipeline_execution
from lza_workbench.workspace.context import (
    WorkspaceContext,
    WorkspaceReadinessLevel,
    load_workspace_context,
)
from lza_workbench.workspace.state import write_workspace_state


@dataclass(frozen=True)
class PipelineStartResult:
    """Structured result of starting a pipeline execution."""

    workspace_dir: Path
    customer_name: str
    pipeline_name: str
    pipeline_arn: str
    profile: str
    region: str
    account_id: str
    dry_run: bool
    execution_id: str | None = None


def start_pipeline_workflow(
    *,
    target_dir: Path | None = None,
    pipeline_name: str | None = None,
    pipeline_type: str = "configuration",
    dry_run: bool = False,
    workspace_context: WorkspaceContext | None = None,
    aws_context: AwsExecutionContext | None = None,
) -> PipelineStartResult:
    """Start an LZA CodePipeline execution and record execution ID in workspace state."""
    ctx = workspace_context or load_workspace_context(
        target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED
    )
    workspace_dir, config, state = ctx.workspace_dir, ctx.config, ctx.state

    pipeline = resolve_pipeline(config, pipeline_type=pipeline_type, pipeline_name=pipeline_name)

    profile = config.aws.profile or ""
    resolved_aws_context = aws_context or resolve_aws_execution_context(
        profile=profile,
        region=config.aws.region,
        role_arn=config.aws.role_arn,
        expected_account_id=config.aws.account_id,
        require_identity=not dry_run,
        require_expected_account=not dry_run,
        prime_credentials=config.aws.prime_credentials,
    )

    region = resolved_aws_context.region
    account_id = (
        resolved_aws_context.identity["account"]
        if resolved_aws_context.identity
        else "UNKNOWN_ACCOUNT"
    )
    pipeline_arn = pipeline.arn(region=region, account_id=account_id)

    if dry_run:
        return PipelineStartResult(
            workspace_dir=workspace_dir,
            customer_name=config.customer.name,
            pipeline_name=pipeline.name,
            pipeline_arn=pipeline_arn,
            profile=profile,
            region=region,
            account_id=account_id,
            dry_run=True,
            execution_id=None,
        )

    client = resolved_aws_context.factory.get_client("codepipeline")
    execution_id = start_pipeline_execution(
        client=client,
        pipeline_name=pipeline.name,
    )

    record_pipeline_execution(
        state,
        execution_id=execution_id,
        pipeline_type=pipeline_type,
    )
    try:
        write_workspace_state(workspace_dir, state)
    except Exception as exc:
        raise LzaError(
            f"Pipeline '{pipeline.name}' started with execution ID '{execution_id}', "
            f"but its ID could not be saved to .lza/state.json: {exc}"
        ) from exc

    return PipelineStartResult(
        workspace_dir=workspace_dir,
        customer_name=config.customer.name,
        pipeline_name=pipeline.name,
        pipeline_arn=pipeline_arn,
        profile=profile,
        region=region,
        account_id=account_id,
        dry_run=False,
        execution_id=execution_id,
    )


__all__ = ["PipelineStartResult", "start_pipeline_workflow"]
