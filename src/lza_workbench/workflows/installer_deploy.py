"""Workflow for deploying the LZA installer CloudFormation stack."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lza_workbench.aws.cloudformation import (
    CfnDeploymentPlanResult,
    CfnStackStatusResult,
    deploy_cloudformation_stack,
    inspect_cloudformation_stack,
    stream_cloudformation_stack_events,
)
from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.errors import LzaError
from lza_workbench.installer.config import InstallerConfigValidationResult
from lza_workbench.installer.deployment import (
    InstallerConfigValidationError,
    inspect_installer_source,
    prepare_installer_template,
    validate_cloudformation_plan,
    validate_deployment_preflight,
)
from lza_workbench.installer.state import record_installer_deployment
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context
from lza_workbench.workspace.state import load_workspace_state, write_workspace_state


@dataclass(frozen=True)
class InstallerDeployResult:
    """Structured result of installer deployment workflow."""

    workspace_dir: Path
    stack_name: str
    operation: str
    cfn_plan: CfnDeploymentPlanResult
    stack_id: str | None
    final_status: CfnStackStatusResult | None
    dry_run: bool
    skipped: bool
    profile: str = ""
    region: str = ""
    account_id: str = ""


def deploy_installer_workflow(
    *,
    target_dir: Path | None = None,
    dry_run: bool = False,
    force: bool = False,
    force_no_change: bool = False,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> InstallerDeployResult:
    """Execute the installer deployment workflow and return structured results."""
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.CONFIGURED)
    workspace_dir, config = ctx.workspace_dir, ctx.config
    profile = config.aws.profile or ""

    validate_deployment_preflight(config)

    try:
        aws_context = resolve_aws_execution_context(
            profile=config.aws.profile,
            region=config.aws.region,
            role_arn=config.aws.role_arn,
            expected_account_id=config.aws.account_id,
            require_identity=True,
            require_expected_account=True,
        )
    except Exception as exc:
        raise LzaError(exc) from exc
    assert aws_context.identity is not None
    account_id = aws_context.identity["account"]

    template_path, resolved_parameters = prepare_installer_template(
        workspace_dir=workspace_dir, config=config, dry_run=dry_run
    )
    inspect_installer_source(factory=aws_context.factory, config=config, region=aws_context.region)

    stack_name = config.installer.stack_name or "AWSAccelerator-InstallerStack"
    cfn_plan = inspect_cloudformation_stack(
        client=aws_context.factory.get_client("cloudformation"),
        stack_name=stack_name,
        resolved_parameters=resolved_parameters,
    )
    operation = validate_cloudformation_plan(cfn_plan)

    if operation == "NO_CHANGE" and not force and not force_no_change:
        return InstallerDeployResult(
            workspace_dir=workspace_dir,
            stack_name=stack_name,
            operation=operation,
            cfn_plan=cfn_plan,
            stack_id=None,
            final_status=None,
            dry_run=dry_run,
            skipped=True,
            profile=profile,
            region=aws_context.region,
            account_id=account_id,
        )

    if operation == "NO_CHANGE" and (force or force_no_change):
        operation = "UPDATE"

    if dry_run:
        return InstallerDeployResult(
            workspace_dir=workspace_dir,
            stack_name=stack_name,
            operation=operation,
            cfn_plan=cfn_plan,
            stack_id=None,
            final_status=None,
            dry_run=True,
            skipped=False,
            profile=profile,
            region=aws_context.region,
            account_id=account_id,
        )

    stack_id = deploy_cloudformation_stack(
        client=aws_context.factory.get_client("cloudformation"),
        stack_name=stack_name,
        template_body=template_path.read_text(encoding="utf-8"),
        parameters=resolved_parameters,
        operation=operation,
    )

    final_status = stream_cloudformation_stack_events(
        client=aws_context.factory.get_client("cloudformation"),
        stack_name=stack_name,
        on_event=on_event,
    )

    if final_status.stack_status not in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}:
        status_name = final_status.stack_status or "UNKNOWN"
        error_detail = f": {final_status.error}" if final_status.error else ""
        raise LzaError(
            f"CloudFormation stack deployment failed with status ({status_name}){error_detail}"
        )

    state = load_workspace_state(workspace_dir)
    record_installer_deployment(
        state,
        aws_identity=aws_context.identity,
        stack_id=final_status.stack_id or stack_id,
        stack_status=final_status.stack_status or "CREATE_COMPLETE",
    )
    write_workspace_state(workspace_dir, state)

    return InstallerDeployResult(
        workspace_dir=workspace_dir,
        stack_name=stack_name,
        operation=operation,
        cfn_plan=cfn_plan,
        stack_id=stack_id,
        final_status=final_status,
        dry_run=False,
        skipped=False,
        profile=profile,
        region=aws_context.region,
        account_id=account_id,
    )


__all__ = [
    "CfnDeploymentPlanResult",
    "CfnStackStatusResult",
    "InstallerConfigValidationError",
    "InstallerConfigValidationResult",
    "InstallerDeployResult",
    "deploy_installer_workflow",
]
