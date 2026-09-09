"""Workflow for gathering root workspace status data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lza_workbench.aws.client_factory import AwsClientFactory
from lza_workbench.aws.cloudformation import get_cloudformation_stack_status
from lza_workbench.aws.codepipeline import (
    get_pipeline_execution,
    get_pipeline_state,
)
from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.aws.s3 import S3ObjectObservation, inspect_s3_object_safe
from lza_workbench.configuration.git import (
    GitRemoteSyncStatus,
    get_git_remote_sync_status,
    get_git_working_tree_status,
)
from lza_workbench.configuration.repository import (
    CONFIG_S3_OBJECT_KEY,
    resolve_s3_configuration_destination,
)
from lza_workbench.configuration.sync import (
    RemoteSyncStatus,
    evaluate_s3_remote_sync,
)
from lza_workbench.installer.deployed_version import resolve_deployed_installer_version
from lza_workbench.pipeline.failures import (
    collect_pipeline_action_failures,
    fetch_codebuild_diagnostics,
)
from lza_workbench.pipeline.resolution import resolve_pipeline
from lza_workbench.workspace.context import (
    WorkspaceAssessment,
    WorkspaceCapability,
    load_workspace_context,
)
from lza_workbench.workspace.schema import WorkspaceConfig, WorkspaceState


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
    git_sync_status: GitRemoteSyncStatus | None = None
    remote_sync: RemoteSyncStatus | None = None
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
    assessment: WorkspaceAssessment | None = None



def _resolve_in_progress_stage_action(pipe_state: Any) -> tuple[str | None, str | None]:
    for stage in pipe_state.stages:
        if stage.status == "InProgress":
            for act in stage.actions:
                if act.status == "InProgress":
                    return stage.stage_name, act.action_name
            action_name = stage.actions[0].action_name if stage.actions else None
            return stage.stage_name, action_name
    return None, None


def _resolve_pipeline_failure_details(
    stages: list[Any], factory: AwsClientFactory | None
) -> tuple[str | None, str | None, str | None]:
    codebuild_client = factory.get_client("codebuild") if factory else None
    logs_client = factory.get_client("logs") if factory else None
    failures = collect_pipeline_action_failures(
        stages,
        fetch_diagnostics=lambda build_id: (
            fetch_codebuild_diagnostics(
                codebuild_client=codebuild_client,
                logs_client=logs_client,
                build_id=build_id,
            )
            if codebuild_client
            else []
        ),
    )
    if not failures:
        return None, None, None
    failed_stage = failures[0].stage_name
    failed_action = failures[0].action_name
    if failures[0].diagnostic_details:
        summary = failures[0].diagnostic_details[0]
    else:
        summary = failures[0].error_message or failures[0].summary
    return failed_stage, failed_action, summary


def _resolve_recorded_pipeline_summary(
    pipeline_type: str, state: WorkspaceState | None, pipeline_name: str
) -> PipelineSummary:
    if pipeline_type == "installer" and state:
        status = state.installer_pipeline_status
        execution_id = state.installer_pipeline_execution_id
        failed_stage = state.installer_pipeline_failed_stage
        failed_action = state.installer_pipeline_failed_action
        failure_summary = state.installer_pipeline_error
    elif pipeline_type == "configuration" and state:
        status = state.config_pipeline_status
        execution_id = state.config_pipeline_execution_id
        failed_stage = state.config_pipeline_failed_stage
        failed_action = state.config_pipeline_failed_action
        failure_summary = state.config_pipeline_error
    else:
        status, execution_id, failed_stage, failed_action, failure_summary = (
            None,
            None,
            None,
            None,
            None,
        )

    return PipelineSummary(
        name=pipeline_name,
        exists=bool(status or execution_id),
        status=status,
        execution_id=execution_id,
        current_stage=None,
        current_action=None,
        failed_stage=failed_stage,
        failed_action=failed_action,
        failure_summary=failure_summary,
        is_live=False,
    )


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

        current_stage, current_action = (
            _resolve_in_progress_stage_action(pipe_state)
            if status == "InProgress"
            else (None, None)
        )

        failed_stage, failed_action, failure_summary = (
            _resolve_pipeline_failure_details(pipe_state.stages, factory)
            if status in {"Failed", "Cancelled"}
            else (None, None, None)
        )

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

    return _resolve_recorded_pipeline_summary(pipeline_type, state, pipeline_name)


def _derive_installer_health(
    installer_stack: InstallerStackSummary,
    installer_pipe: PipelineSummary,
) -> str:
    if not installer_stack.exists or installer_stack.status in (None, "NOT_DEPLOYED"):
        return "Incomplete"
    if (
        installer_stack.status
        in (
            "CREATE_IN_PROGRESS",
            "UPDATE_IN_PROGRESS",
            "ROLLBACK_IN_PROGRESS",
        )
        or installer_pipe.status == "InProgress"
    ):
        return "Running"
    if (
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
        return "Failed"
    if installer_stack.status in ("CREATE_COMPLETE", "UPDATE_COMPLETE", "IMPORT_COMPLETE") and (
        installer_pipe.status in ("Succeeded", None, "Not Started")
    ):
        return "Healthy"
    return "Attention Required"


def _derive_configuration_health(
    config_repo: ConfigurationRepoSummary,
    config_pipe: PipelineSummary,
) -> str:
    if config_pipe.status == "InProgress":
        return "Running"
    if config_pipe.status in ("Failed", "Cancelled"):
        return "Failed"
    if not config_repo.local_git_clean or (
        config_repo.remote_sync is not None
        and config_repo.remote_sync.status == "Diverged"
    ) or (
        config_repo.git_sync_status is not None
        and config_repo.git_sync_status.status == "Diverged"
    ):
        return "Attention Required"
    if config_pipe.status == "Succeeded":
        return "Healthy"
    if not config_pipe.exists or config_pipe.status in (None, "Not Deployed", "Not Started"):
        return "Incomplete"
    return "Attention Required"


def _derive_workspace_health(
    installer_health: str,
    configuration_health: str,
) -> str:
    if (
        installer_health == "Failed"
        or configuration_health == "Failed"
        or installer_health == "Attention Required"
        or configuration_health == "Attention Required"
    ):
        return "Attention Required"
    if installer_health == "Running" or configuration_health == "Running":
        return "Running"
    if installer_health == "Incomplete" or configuration_health == "Incomplete":
        return "Incomplete"
    if installer_health == "Healthy" and configuration_health == "Healthy":
        return "Healthy"
    return "Attention Required"


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

    installer_health = _derive_installer_health(installer_stack, installer_pipe)
    configuration_health = _derive_configuration_health(config_repo, config_pipe)
    workspace_health = _derive_workspace_health(installer_health, configuration_health)

    return OverallHealthSummary(
        installer=installer_health,
        configuration=configuration_health,
        workspace=workspace_health,
        is_live=True,
    )


def _resolve_installer_stack_summary(
    config: WorkspaceConfig,
    state: WorkspaceState | None,
    factory: AwsClientFactory | None,
    is_live: bool,
) -> InstallerStackSummary:
    cfn_stack_name = config.installer.stack_name or "AWSAccelerator-InstallerStack"
    if is_live and factory is not None:
        cfn_client = factory.get_client("cloudformation")
        cfn_status = get_cloudformation_stack_status(client=cfn_client, stack_name=cfn_stack_name)
        ssm_client = factory.get_client("ssm") if cfn_status.exists else None
        deployed_version = (
            resolve_deployed_installer_version(
                cfn_client=cfn_client,
                ssm_client=ssm_client,
                stack_name=cfn_stack_name,
                accelerator_prefix=(
                    cfn_status.deployed_parameters.get("AcceleratorPrefix")
                    or config.lza.accelerator_prefix
                ),
            )
            if cfn_status.exists
            else None
        )
        return InstallerStackSummary(
            name=cfn_stack_name,
            status=cfn_status.stack_status,
            exists=cfn_status.exists,
            deployed_version=deployed_version or config.lza.version,
            is_live=True,
        )

    recorded_status = state.installer_stack_status if state else None
    recorded_version = state.installer_template_version if state else None
    return InstallerStackSummary(
        name=cfn_stack_name,
        status=recorded_status,
        exists=bool(recorded_status),
        deployed_version=recorded_version,
        is_live=False,
    )


def _resolve_repo_target(
    repo: Any,
    config: WorkspaceConfig,
    state: WorkspaceState | None,
    aws_identity: dict[str, Any] | None,
    region: str | None,
) -> str | None:
    if repo.type == "s3":
        try:
            return resolve_s3_configuration_destination(
                configured_bucket=repo.bucket,
                account_id=(
                    config.aws.account_id
                    or (state.management_account_id if state else None)
                    or (aws_identity.get("account") if aws_identity else None)
                ),
                region=region or config.aws.region,
            ).bucket
        except Exception:
            return repo.bucket or "Not configured"
    if repo.type == "codecommit":
        return repo.repository_name or "aws-accelerator-config"
    if repo.type == "codeconnection":
        if repo.owner and repo.repository_name:
            return f"{repo.owner}/{repo.repository_name}"
        return repo.repository_name or "Not configured"
    if repo.type == "git":
        return repo.repository or repo.repository_name or "Not configured"
    return None


def _resolve_remote_sync_status(
    repo: Any,
    config: WorkspaceConfig,
    config_dir: Path,
    target: str | None,
    git_sync_status: Any,
    factory: AwsClientFactory | None,
    state: WorkspaceState | None,
    is_live: bool,
) -> RemoteSyncStatus | None:
    if repo.type == "s3":
        s3_info: S3ObjectObservation | None = None
        if is_live and target and target != "Not configured" and factory is not None:
            try:
                s3_client = factory.get_client("s3")
                s3_info = inspect_s3_object_safe(
                    client=s3_client,
                    bucket_name=target,
                    object_key=CONFIG_S3_OBJECT_KEY,
                )
            except Exception:
                s3_info = None
        exclude_dirs = set(config.configuration.packaging.exclude.directories)
        exclude_files = set(config.configuration.packaging.exclude.files)
        return evaluate_s3_remote_sync(
            config_dir=config_dir,
            exclude_dirs=exclude_dirs,
            exclude_files=exclude_files,
            s3_object_info=s3_info,
            state=state,
            is_live=is_live,
        )
    if git_sync_status is not None:
        return RemoteSyncStatus.from_git_sync(git_sync_status)
    return None


def get_root_status_workflow(
    *,
    target_dir: Path | None = None,
) -> RootStatusResult:
    """Query workspace and AWS to collect root summary status."""
    ctx = load_workspace_context(
        target_dir, required_capabilities=(WorkspaceCapability.METADATA_VALID,)
    )
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

    installer_stack_summary = _resolve_installer_stack_summary(
        config=config,
        state=state,
        factory=factory,
        is_live=is_live,
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
    config_dir = (
        ctx.config_dir
        if isinstance(getattr(ctx, "config_dir", None), Path)
        else (workspace_dir / config.configuration.local_path)
    )
    config_dir_exists = config_dir.exists()
    repo = config.configuration.repository

    target = _resolve_repo_target(
        repo=repo,
        config=config,
        state=state,
        aws_identity=aws_identity,
        region=region,
    )

    gwt = get_git_working_tree_status(config_dir) if config_dir_exists else None
    local_git_branch = gwt.branch if gwt else None
    local_git_clean = not gwt.has_uncommitted if gwt else True
    local_git_uncommitted = gwt.uncommitted_count if gwt else 0

    git_sync_status = (
        get_git_remote_sync_status(config_dir, branch=repo.branch)
        if gwt is not None
        else None
    )

    remote_sync = _resolve_remote_sync_status(
        repo=repo,
        config=config,
        config_dir=config_dir,
        target=target,
        git_sync_status=git_sync_status,
        factory=factory,
        state=state,
        is_live=is_live,
    )

    config_repo_summary = ConfigurationRepoSummary(
        repository_type=repo.type,
        target=target,
        local_git_branch=local_git_branch,
        local_git_clean=local_git_clean,
        local_git_uncommitted=local_git_uncommitted,
        git_sync_status=git_sync_status,
        remote_sync=remote_sync,
        is_live=is_live,
    )

    health = _derive_overall_health(
        is_live=is_live,
        installer_stack=installer_stack_summary,
        installer_pipe=installer_pipe_summary,
        config_repo=config_repo_summary,
        config_pipe=config_pipe_summary,
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
        assessment=ctx.assessment,
    )


__all__ = [
    "ConfigurationRepoSummary",
    "InstallerStackSummary",
    "OverallHealthSummary",
    "PipelineSummary",
    "RootStatusResult",
    "get_root_status_workflow",
]
