"""Workflow for gathering root workspace status data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lza_workbench.aws.client_factory import AwsClientFactory
from lza_workbench.aws.cloudformation import get_cloudformation_stack_status
from lza_workbench.aws.codebuild import (
    fetch_codebuild_diagnostics,
    normalize_root_cause_and_resource,
)
from lza_workbench.aws.codepipeline import (
    get_pipeline_execution,
    get_pipeline_state,
)
from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.configuration.git import (
    get_git_remote_sync_status,
    get_git_working_tree_status,
)
from lza_workbench.configuration.repository import resolve_s3_configuration_destination
from lza_workbench.installer.versions import branch_to_version
from lza_workbench.pipeline.failures import collect_pipeline_action_failures
from lza_workbench.pipeline.resolution import resolve_pipeline
from lza_workbench.workflows.status_config import (
    ConfigurationStatusResult,
    get_config_status_workflow,
)
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context
from lza_workbench.workspace.schema import WorkspaceState


@dataclass(frozen=True)
class PipelineSummary:
    """Concise operational summary of a CodePipeline."""

    name: str
    exists: bool = False
    status: str | None = None
    execution_id: str | None = None
    start_time: str | None = None
    duration_seconds: float | None = None
    current_stage: str | None = None
    current_action: str | None = None
    failed_stage: str | None = None
    failed_action: str | None = None
    failure_summary: str | None = None
    is_live: bool = True


@dataclass(frozen=True)
class InstallerStackSummary:
    """Concise operational summary of the CloudFormation installer stack."""

    name: str
    status: str | None = None
    exists: bool = False
    deployed_version: str | None = None
    is_live: bool = True


@dataclass(frozen=True)
class ConfigurationRepoSummary:
    """Concise operational summary of configuration repository and local git state."""

    repository_type: str
    target: str | None = None
    local_git_branch: str | None = None
    local_git_clean: bool = True
    local_git_uncommitted: int = 0
    remote_sync_summary: str | None = None
    is_live: bool = True


@dataclass(frozen=True)
class OverallHealthSummary:
    """Concise overall deployment health summary."""

    installer: str
    configuration: str
    workspace: str
    is_live: bool = True


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
    installer: InstallerStackSummary
    installer_pipeline: PipelineSummary
    configuration_repo: ConfigurationRepoSummary
    configuration_pipeline: PipelineSummary
    health: OverallHealthSummary
    stack_name: str
    stack_status: str | None
    stack_exists: bool
    repository_type: str
    config_dir: Path
    config_dir_exists: bool
    installer_pipeline_name: str
    config_pipeline_name: str
    config_status: ConfigurationStatusResult | None = None


def _resolve_pipeline_summary(
    *,
    pipeline_name: str,
    pipeline_type: str,
    is_live: bool,
    factory: AwsClientFactory | None,
    codepipeline_client: Any | None,
    state: WorkspaceState | None,
) -> PipelineSummary:
    """Resolve pipeline execution details from live AWS CodePipeline or recorded state."""
    if is_live and codepipeline_client is not None:
        pipe_state = get_pipeline_state(client=codepipeline_client, pipeline_name=pipeline_name)
        if not pipe_state.exists:
            return PipelineSummary(
                name=pipeline_name,
                exists=False,
                status="Not Deployed",
                is_live=True,
            )

        status = pipe_state.status
        execution_id = pipe_state.latest_execution_id
        start_time: str | None = None
        duration_seconds: float | None = None

        if execution_id:
            exec_res = get_pipeline_execution(
                client=codepipeline_client,
                pipeline_name=pipeline_name,
                execution_id=execution_id,
            )
            start_time = exec_res.start_time
            duration_seconds = exec_res.duration_seconds

        current_stage: str | None = None
        current_action: str | None = None
        if status == "InProgress":
            for stage in pipe_state.stage_states:
                if getattr(stage, "status", None) == "InProgress":
                    current_stage = getattr(stage, "stage_name", None)
                    for act in getattr(stage, "actions", []):
                        if getattr(act, "status", None) == "InProgress":
                            current_action = getattr(act, "action_name", None)
                            break
                    if not current_action and getattr(stage, "actions", None):
                        current_action = stage.actions[0].action_name
                    break

        failed_stage: str | None = None
        failed_action: str | None = None
        failure_summary: str | None = None
        if status in {"Failed", "Cancelled"}:
            failures = collect_pipeline_action_failures(
                pipe_state.stage_states,
                fetch_diagnostics=lambda build_id: (
                    fetch_codebuild_diagnostics(factory=factory, build_id=build_id)
                    if factory
                    else []
                ),
                normalize_diagnostic=normalize_root_cause_and_resource,
            )
            if failures:
                failed_stage = failures[0].stage_name
                failed_action = failures[0].action_name
                if failures[0].diagnostic_details:
                    failure_summary = failures[0].diagnostic_details[0]
                else:
                    failure_summary = failures[0].error_message or failures[0].summary

        return PipelineSummary(
            name=pipeline_name,
            exists=True,
            status=status,
            execution_id=execution_id,
            start_time=start_time,
            duration_seconds=duration_seconds,
            current_stage=current_stage,
            current_action=current_action,
            failed_stage=failed_stage,
            failed_action=failed_action,
            failure_summary=failure_summary,
            is_live=True,
        )

    # Fallback to recorded state
    if pipeline_type == "installer" and state:
        status = state.installer_pipeline_status
        execution_id = state.installer_pipeline_execution_id
        failed_stage = state.installer_pipeline_failed_stage
        failed_action = state.installer_pipeline_failed_action
        failure_summary = state.installer_pipeline_error
        exists = bool(status or execution_id)
    elif pipeline_type == "configuration" and state:
        status = state.config_pipeline_status
        execution_id = state.config_pipeline_execution_id
        failed_stage = state.config_pipeline_failed_stage
        failed_action = state.config_pipeline_failed_action
        failure_summary = state.config_pipeline_error
        exists = bool(status or execution_id)
    else:
        status = None
        execution_id = None
        failed_stage = None
        failed_action = None
        failure_summary = None
        exists = False

    return PipelineSummary(
        name=pipeline_name,
        exists=exists,
        status=status,
        execution_id=execution_id,
        current_stage=None,
        current_action=None,
        failed_stage=failed_stage,
        failed_action=failed_action,
        failure_summary=failure_summary,
        is_live=False,
    )


def _derive_overall_health(
    *,
    is_live: bool,
    installer_stack: InstallerStackSummary,
    installer_pipe: PipelineSummary,
    config_repo: ConfigurationRepoSummary,
    config_pipe: PipelineSummary,
) -> OverallHealthSummary:
    """Derive simple health states (Healthy, Running, Attention Required, Incomplete, Degraded)."""
    if not is_live:
        inst_status = installer_pipe.status or installer_stack.status
        installer_health = f"Recorded: {inst_status}" if inst_status else "Unknown"
        config_status = config_pipe.status
        configuration_health = f"Recorded: {config_status}" if config_status else "Unknown"
        has_any_state = bool(inst_status or config_status)
        workspace_health = (
            "AWS Unavailable - Showing Last Known State"
            if has_any_state
            else "AWS Unavailable - No Recorded State"
        )
        return OverallHealthSummary(
            installer=installer_health,
            configuration=configuration_health,
            workspace=workspace_health,
            is_live=False,
        )

    # Live evaluation
    # 1. Installer health
    if not installer_stack.exists or installer_stack.status in (None, "NOT_DEPLOYED"):
        installer_health = "Incomplete"
    elif (
        installer_stack.status
        in (
            "CREATE_IN_PROGRESS",
            "UPDATE_IN_PROGRESS",
            "ROLLBACK_IN_PROGRESS",
        )
        or installer_pipe.status == "InProgress"
    ):
        installer_health = "Running"
    elif (
        installer_stack.status
        in (
            "CREATE_FAILED",
            "UPDATE_FAILED",
            "UPDATE_ROLLBACK_FAILED",
            "ROLLBACK_FAILED",
            "UPDATE_ROLLBACK_COMPLETE",
            "ROLLBACK_COMPLETE",
        )
        or installer_pipe.status in ("Failed", "Cancelled")
    ):
        installer_health = "Failed"
    elif installer_stack.status in ("CREATE_COMPLETE", "UPDATE_COMPLETE", "IMPORT_COMPLETE") and (
        installer_pipe.status in ("Succeeded", None, "Not Started")
    ):
        installer_health = "Healthy"
    else:
        installer_health = "Attention Required"

    # 2. Configuration health
    if config_pipe.status == "InProgress":
        configuration_health = "Running"
    elif config_pipe.status in ("Failed", "Cancelled"):
        configuration_health = "Failed"
    elif not config_repo.local_git_clean or (
        config_repo.remote_sync_summary and "Diverged" in config_repo.remote_sync_summary
    ):
        configuration_health = "Attention Required"
    elif config_pipe.status == "Succeeded":
        configuration_health = "Healthy"
    elif not config_pipe.exists or config_pipe.status in (None, "Not Deployed", "Not Started"):
        configuration_health = "Incomplete"
    else:
        configuration_health = "Attention Required"

    # 3. Overall workspace health
    if (
        installer_health == "Failed"
        or configuration_health == "Failed"
        or installer_health == "Attention Required"
        or configuration_health == "Attention Required"
    ):
        workspace_health = "Attention Required"
    elif installer_health == "Running" or configuration_health == "Running":
        workspace_health = "Running"
    elif installer_health == "Incomplete" or configuration_health == "Incomplete":
        workspace_health = "Incomplete"
    elif installer_health == "Healthy" and configuration_health == "Healthy":
        workspace_health = "Healthy"
    else:
        workspace_health = "Attention Required"

    return OverallHealthSummary(
        installer=installer_health,
        configuration=configuration_health,
        workspace=workspace_health,
        is_live=True,
    )


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
        prime_credentials=config.aws.prime_credentials,
    )
    factory = aws_context.factory
    region = aws_context.region
    aws_identity = aws_context.identity
    aws_error = aws_context.error
    is_live = aws_identity is not None

    # Installer Stack
    cfn_stack_name = config.installer.stack_name or "AWSAccelerator-InstallerStack"
    if is_live:
        cfn_client = factory.get_client("cloudformation")
        cfn_status = get_cloudformation_stack_status(client=cfn_client, stack_name=cfn_stack_name)
        deployed_version = (
            branch_to_version(cfn_status.deployed_parameters.get("RepositoryBranchName", ""))
            if cfn_status.exists
            else None
        )
        installer_stack_summary = InstallerStackSummary(
            name=cfn_stack_name,
            status=cfn_status.stack_status,
            exists=cfn_status.exists,
            deployed_version=deployed_version,
            is_live=True,
        )
    else:
        recorded_status = state.installer_stack_status if state else None
        recorded_version = state.installer_template_version if state else None
        installer_stack_summary = InstallerStackSummary(
            name=cfn_stack_name,
            status=recorded_status,
            exists=bool(recorded_status),
            deployed_version=recorded_version,
            is_live=False,
        )

    # Pipelines
    codepipeline_client = factory.get_client("codepipeline") if is_live else None
    installer_pipeline_name = resolve_pipeline(config, pipeline_type="installer").name
    config_pipeline_name = resolve_pipeline(config, pipeline_type="configuration").name

    installer_pipe_summary = _resolve_pipeline_summary(
        pipeline_name=installer_pipeline_name,
        pipeline_type="installer",
        is_live=is_live,
        factory=factory if is_live else None,
        codepipeline_client=codepipeline_client,
        state=state,
    )
    config_pipe_summary = _resolve_pipeline_summary(
        pipeline_name=config_pipeline_name,
        pipeline_type="configuration",
        is_live=is_live,
        factory=factory if is_live else None,
        codepipeline_client=codepipeline_client,
        state=state,
    )

    # Configuration Repository & Local Git
    config_dir = workspace_dir / config.configuration.local_path
    config_dir_exists = config_dir.exists()
    repo = config.configuration.repository

    target = None
    if repo.type == "s3":
        try:
            target = resolve_s3_configuration_destination(
                configured_bucket=repo.bucket,
                account_id=(
                    config.aws.account_id
                    or (state.management_account_id if state else None)
                    or (aws_identity.get("account") if aws_identity else None)
                ),
                region=region or config.aws.region,
            ).bucket
        except Exception:
            target = repo.bucket or "Not configured"
    elif repo.type == "codecommit":
        target = repo.repository_name or "aws-accelerator-config"
    elif repo.type == "codeconnection":
        if repo.owner and repo.repository_name:
            target = f"{repo.owner}/{repo.repository_name}"
        else:
            target = repo.repository_name or "Not configured"
    elif repo.type == "git":
        target = repo.repository or repo.repository_name or "Not configured"

    gwt = get_git_working_tree_status(config_dir) if config_dir_exists else None
    local_git_branch = gwt.branch if gwt else None
    local_git_clean = not gwt.has_uncommitted if gwt else True
    local_git_uncommitted = gwt.uncommitted_count if gwt else 0

    if gwt and is_live:
        sync_res = get_git_remote_sync_status(config_dir, branch=repo.branch)
        remote_sync_summary = sync_res.summary if sync_res else None
    elif not is_live:
        remote_sync_summary = "Not Checked (AWS Unavailable)"
    else:
        remote_sync_summary = "Not Git"

    config_repo_summary = ConfigurationRepoSummary(
        repository_type=repo.type,
        target=target,
        local_git_branch=local_git_branch,
        local_git_clean=local_git_clean,
        local_git_uncommitted=local_git_uncommitted,
        remote_sync_summary=remote_sync_summary,
        is_live=is_live,
    )

    # Overall Health
    health = _derive_overall_health(
        is_live=is_live,
        installer_stack=installer_stack_summary,
        installer_pipe=installer_pipe_summary,
        config_repo=config_repo_summary,
        config_pipe=config_pipe_summary,
    )

    # Full ConfigurationStatusResult for detailed inspection or compatibility
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
        installer=installer_stack_summary,
        installer_pipeline=installer_pipe_summary,
        configuration_repo=config_repo_summary,
        configuration_pipeline=config_pipe_summary,
        health=health,
        stack_name=installer_stack_summary.name,
        stack_status=installer_stack_summary.status,
        stack_exists=installer_stack_summary.exists,
        repository_type=repo.type,
        config_dir=config_dir,
        config_dir_exists=config_dir_exists,
        installer_pipeline_name=installer_pipeline_name,
        config_pipeline_name=config_pipeline_name,
        config_status=config_status,
    )


__all__ = [
    "ConfigurationRepoSummary",
    "InstallerStackSummary",
    "OverallHealthSummary",
    "PipelineSummary",
    "RootStatusResult",
    "get_root_status_workflow",
]
