"""Workflow for gathering root workspace status data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lza_workbench.aws.cloudformation import get_cloudformation_stack_status
from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.pipeline.resolution import resolve_pipeline
from lza_workbench.workflows.status_config import (
    ConfigurationStatusResult,
    get_config_status_workflow,
)
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context


@dataclass(frozen=True)
class RootStatusResult:
    """All data needed to render the root workspace status report."""

    workspace_dir: Path
    customer_name: str
    lza_version: str
    profile: str
    region: str
    aws_identity: dict[str, str] | None
    aws_error: str | None
    stack_name: str
    stack_status: str | None
    stack_exists: bool
    repository_type: str
    config_dir: Path
    config_dir_exists: bool
    installer_pipeline_name: str
    config_pipeline_name: str
    config_status: ConfigurationStatusResult | None = None


def get_root_status_workflow(
    *,
    target_dir: Path | None = None,
) -> RootStatusResult:
    """Query workspace and AWS to collect root summary status."""
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED)
    workspace_dir, config, state = ctx.workspace_dir, ctx.config, ctx.state

    profile = config.aws.profile or ""
    aws_context = resolve_aws_execution_context(
        profile=profile,
        region=config.aws.region,
        role_arn=config.aws.role_arn,
        expected_account_id=config.aws.account_id,
    )
    factory = aws_context.factory
    region = aws_context.region
    aws_identity = aws_context.identity
    aws_error = aws_context.error

    cfn_stack_name = config.installer.stack_name or "AWSAccelerator-InstallerStack"
    cfn_client = factory.get_client("cloudformation") if aws_identity else None
    cfn_status = get_cloudformation_stack_status(client=cfn_client, stack_name=cfn_stack_name)

    config_status = get_config_status_workflow(
        config=config,
        state=state,
        workspace_dir=workspace_dir,
    )

    return RootStatusResult(
        workspace_dir=workspace_dir,
        customer_name=config.customer.name,
        lza_version=config.lza.version,
        profile=profile,
        region=region,
        aws_identity=aws_identity,
        aws_error=aws_error,
        stack_name=cfn_stack_name,
        stack_status=cfn_status.stack_status,
        stack_exists=cfn_status.exists,
        repository_type=config.configuration.repository.type,
        config_dir=workspace_dir / config.configuration.local_path,
        config_dir_exists=(workspace_dir / config.configuration.local_path).exists(),
        installer_pipeline_name=resolve_pipeline(config, pipeline_type="installer").name,
        config_pipeline_name=resolve_pipeline(config, pipeline_type="configuration").name,
        config_status=config_status,
    )


__all__ = [
    "RootStatusResult",
    "get_root_status_workflow",
]
