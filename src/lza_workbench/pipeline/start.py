"""Workflow for starting AWS CodePipeline executions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lza_workbench.errors import LzaError
from lza_workbench.infrastructure.aws.codepipeline import (
    get_pipeline_state,
    start_pipeline_execution,
)
from lza_workbench.infrastructure.aws.session import (
    AwsExecutionContext,
    resolve_aws_execution_context,
)
from lza_workbench.pipeline.resolution import resolve_pipeline
from lza_workbench.pipeline.state import record_pipeline_started
from lza_workbench.workspace.context import (
    WorkspaceContext,
    load_workspace_context,
)
from lza_workbench.workspace.persistence import update_workspace_state
from lza_workbench.workspace.schema import CustomerEnvironmentTarget, WorkspaceState
from lza_workbench.workspace.validation import WorkspaceCapability


@dataclass(frozen=True)
class PipelineStartResult:
    workspace_dir: Path | None
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
    accelerator_prefix: str = "AWSAccelerator",
    customer_name: str | None = None,
    dry_run: bool = False,
    allow_concurrent: bool = False,
    environment_target: CustomerEnvironmentTarget | None = None,
    workspace_context: WorkspaceContext | None = None,
    aws_context: AwsExecutionContext | None = None,
) -> PipelineStartResult:
    """Start an LZA CodePipeline execution and optionally record it in workspace state."""
    ctx = workspace_context
    if ctx is None and (target_dir is not None or aws_context is None):
        ctx = load_workspace_context(
            target_dir, required_capabilities=(WorkspaceCapability.METADATA_VALID,)
        )

    workspace_dir = ctx.workspace_dir if ctx is not None else None
    config = ctx.config if ctx is not None else None
    state = ctx.state if ctx is not None else None
    env_target = environment_target or (config.environment_target if config is not None else None)

    pipeline = resolve_pipeline(
        env_target,
        pipeline_type=pipeline_type,
        pipeline_name=pipeline_name,
        accelerator_prefix=accelerator_prefix,
    )

    profile = (config.aws.profile or "") if config is not None else (
        aws_context.factory.profile or "" if aws_context is not None else ""
    )
    expected_account_id = env_target.account_id if env_target is not None else None
    if aws_context is not None:
        resolved_aws_context = aws_context
        if not dry_run and expected_account_id is not None:
            resolved_aws_context.require_live(expected_account_id=expected_account_id)
    elif config is not None:
        resolved_aws_context = resolve_aws_execution_context(
            profile=profile,
            region=config.aws.region,
            role_arn=config.aws.role_arn,
            expected_account_id=expected_account_id,
            require_identity=not dry_run,
            require_expected_account=not dry_run,
            prime_credentials=config.aws.prime_credentials,
        )
    else:
        raise LzaError("Pipeline execution requires an AWS execution context or workspace.")

    region = resolved_aws_context.region
    account_id = (
        resolved_aws_context.identity["account"]
        if resolved_aws_context.identity
        else "UNKNOWN_ACCOUNT"
    )
    pipeline_arn = pipeline.arn(region=region, account_id=account_id)
    resolved_customer_name = (
        customer_name
        if customer_name is not None
        else (env_target.customer.name if env_target is not None else "")
    )

    if dry_run:
        return PipelineStartResult(
            workspace_dir=workspace_dir,
            customer_name=resolved_customer_name,
            pipeline_name=pipeline.name,
            pipeline_arn=pipeline_arn,
            profile=profile,
            region=region,
            account_id=account_id,
            dry_run=True,
            execution_id=None,
        )

    client = resolved_aws_context.factory.get_client("codepipeline")
    if not allow_concurrent:
        pipeline_state = get_pipeline_state(client=client, pipeline_name=pipeline.name)
        if pipeline_state.status == "InProgress":
            raise LzaError(
                f"Pipeline '{pipeline.name}' already has an execution in progress. "
                "Wait for it to finish or use --allow-concurrent to start another execution."
            )

    execution_id = start_pipeline_execution(
        client=client,
        pipeline_name=pipeline.name,
    )

    if workspace_dir is not None and state is not None:
        def _record_start(current: WorkspaceState) -> None:
            record_pipeline_started(
                current,
                execution_id=execution_id,
                pipeline_name=pipeline.name,
                pipeline_type=pipeline_type,
            )

        _record_start(state)
        try:
            update_workspace_state(workspace_dir, _record_start)
        except Exception as exc:
            raise LzaError(
                f"Pipeline '{pipeline.name}' started with execution ID '{execution_id}', "
                f"but its ID could not be saved to .lza/state.json: {exc}"
            ) from exc

    return PipelineStartResult(
        workspace_dir=workspace_dir,
        customer_name=resolved_customer_name,
        pipeline_name=pipeline.name,
        pipeline_arn=pipeline_arn,
        profile=profile,
        region=region,
        account_id=account_id,
        dry_run=False,
        execution_id=execution_id,
    )


__all__ = ["PipelineStartResult", "start_pipeline_workflow"]
