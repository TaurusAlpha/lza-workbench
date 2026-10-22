"""Configuration status interpretation, inspection, and reporting workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lza_workbench.configuration.git import (
    GitRemoteSyncStatus,
    get_git_remote_sync_status,
    get_git_working_tree_status,
)
from lza_workbench.configuration.inspection import (
    CodeCommitConfigurationRepositoryStatus,
    CodeConnectionConfigurationRepositoryStatus,
    ConfigurationPipelineActionFailure,
    ConfigurationPipelineStatus,
    ConfigurationRepositoryStatus,
    ConfigurationStatusResult,
    ConfigurationSynchronizationStatus,
    ConfigurationWorkspaceStatus,
    GitConfigurationRepositoryStatus,
    LocalGitStatus,
    S3ConfigurationRepositoryStatus,
    inspect_configuration_pipeline,
    inspect_configuration_repository,
)
from lza_workbench.configuration.repository import (
    CONFIG_S3_OBJECT_KEY,
    resolve_s3_configuration_destination,
)
from lza_workbench.configuration.sync import (
    RemoteSyncStatus,
    evaluate_s3_remote_sync,
)
from lza_workbench.configuration.templates import capture_init_values_snapshot
from lza_workbench.configuration.warnings import compile_configuration_warnings
from lza_workbench.infrastructure.aws.codecommit import inspect_codecommit_repository
from lza_workbench.infrastructure.aws.codeconnections import inspect_codeconnection
from lza_workbench.infrastructure.aws.errors import (
    ObservationOutcome,
    classify_aws_error,
    outcome_from_aws_error,
)
from lza_workbench.infrastructure.aws.s3 import inspect_s3_object_safe
from lza_workbench.infrastructure.aws.session import (
    AwsExecutionContext,
    resolve_aws_execution_context,
)
from lza_workbench.workspace.context import load_workspace_context
from lza_workbench.workspace.schema import (
    CustomerEnvironmentTarget,
    WorkspaceConfig,
    WorkspaceState,
)
from lza_workbench.workspace.validation import WorkspaceCapability

if TYPE_CHECKING:
    from lza_workbench.infrastructure.aws.session import AwsClientFactory


@dataclass(frozen=True)
class ConfigurationRepoSummary:
    repository_type: str
    target: str | None = None
    local_git_branch: str | None = None
    local_git_clean: bool = True
    local_git_uncommitted: int = 0
    git_sync_status: GitRemoteSyncStatus | None = None
    remote_sync: RemoteSyncStatus | None = None
    is_live: bool = True
    outcome: ObservationOutcome = ObservationOutcome.NOT_COLLECTED
    observed_at: datetime | None = None
    last_attempt_at: datetime | None = None
    error: str | None = None


def _resolve_repo_target(
    target: CustomerEnvironmentTarget,
    state: WorkspaceState | None,
    aws_identity: dict[str, Any] | None,
    region: str | None,
) -> str | None:
    repo = target.configuration_repository
    if repo.type == "s3":
        try:
            return resolve_s3_configuration_destination(
                configured_bucket=repo.bucket,
                account_id=(
                    target.account_id
                    or (state.observed_account_id if state else None)
                    or (aws_identity.get("account") if aws_identity else None)
                ),
                region=region or target.region,
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


def observe_configuration_repository(
    *,
    target: CustomerEnvironmentTarget,
    factory: AwsClientFactory | None = None,
    config_dir: Path | None = None,
    resolved_config: WorkspaceConfig | None = None,
    state: WorkspaceState | None = None,
    aws_identity: dict[str, Any] | None = None,
    region: str | None = None,
) -> ConfigurationRepoSummary:
    """Collect unified configuration repository observation and local git synchronization."""
    now = datetime.now(UTC)
    repo = target.configuration_repository
    resolved_target = _resolve_repo_target(target, state, aws_identity, region)

    is_live = False
    outcome = ObservationOutcome.NOT_COLLECTED
    error: str | None = None
    last_attempt_at: datetime | None = None
    observed_at: datetime | None = None

    config_dir_exists = config_dir.exists() if config_dir is not None else False
    gwt = (
        get_git_working_tree_status(config_dir)
        if config_dir is not None and config_dir_exists
        else None
    )
    local_git_branch = gwt.branch if gwt else None
    local_git_clean = not gwt.has_uncommitted if gwt else True
    local_git_uncommitted = gwt.uncommitted_count if gwt else 0

    git_sync_status = (
        get_git_remote_sync_status(config_dir, branch=repo.branch)
        if config_dir is not None and gwt is not None
        else None
    )

    remote_sync: RemoteSyncStatus | None = None
    if repo.type == "s3":
        s3_info = None
        if (
            aws_identity is not None
            and factory is not None
            and resolved_target
            and resolved_target != "Not configured"
        ):
            last_attempt_at = now
            try:
                s3_client = factory.get_client("s3")
                s3_info = inspect_s3_object_safe(
                    client=s3_client,
                    bucket_name=resolved_target,
                    object_key=CONFIG_S3_OBJECT_KEY,
                )
                if s3_info.error:
                    error = s3_info.error
                    outcome = (
                        outcome_from_aws_error(s3_info.error_info)
                        if s3_info.error_info is not None
                        else ObservationOutcome.COLLECTION_FAILED
                    )
                    is_live = False
                elif not s3_info.exists:
                    outcome = ObservationOutcome.ABSENT
                    is_live = True
                    observed_at = now
                else:
                    outcome = ObservationOutcome.OBSERVED
                    is_live = True
                    observed_at = now
            except Exception as exc:
                info = classify_aws_error(exc)
                outcome = outcome_from_aws_error(info)
                error = str(exc)
                is_live = False

        if config_dir is not None:
            exclude_dirs = (
                set(resolved_config.configuration.packaging.exclude.directories)
                if resolved_config is not None
                else {".git"}
            )
            exclude_files = (
                set(resolved_config.configuration.packaging.exclude.files)
                if resolved_config is not None
                else {".DS_Store"}
            )
            remote_sync = evaluate_s3_remote_sync(
                config_dir=config_dir,
                exclude_dirs=exclude_dirs,
                exclude_files=exclude_files,
                s3_object_info=s3_info,
                state=state,
                is_live=is_live,
            )
    elif repo.type == "codecommit":
        if aws_identity is not None and factory is not None:
            last_attempt_at = now
            try:
                cc_client = factory.get_client("codecommit")
                cc_info = inspect_codecommit_repository(
                    client=cc_client,
                    repository_name=repo.repository_name or "aws-accelerator-config",
                    branch_name=repo.branch or "main",
                )
                if cc_info.error:
                    error = cc_info.error
                    outcome = (
                        outcome_from_aws_error(cc_info.error_info)
                        if cc_info.error_info is not None
                        else ObservationOutcome.COLLECTION_FAILED
                    )
                    is_live = False
                elif not cc_info.exists:
                    outcome = ObservationOutcome.ABSENT
                    is_live = True
                    observed_at = now
                else:
                    outcome = ObservationOutcome.OBSERVED
                    is_live = True
                    observed_at = now
            except Exception as exc:
                info = classify_aws_error(exc)
                outcome = outcome_from_aws_error(info)
                error = str(exc)
                is_live = False
        if git_sync_status is not None:
            remote_sync = RemoteSyncStatus.from_git_sync(git_sync_status)
    elif repo.type == "codeconnection":
        if aws_identity is not None and factory is not None and repo.codeconnection_arn:
            last_attempt_at = now
            try:
                conn_client = factory.get_client("codeconnections")
                conn_res = inspect_codeconnection(
                    client=conn_client,
                    connection_arn=repo.codeconnection_arn,
                )
                if conn_res.error:
                    error = conn_res.error
                    outcome = (
                        outcome_from_aws_error(conn_res.error_info)
                        if conn_res.error_info is not None
                        else ObservationOutcome.COLLECTION_FAILED
                    )
                    is_live = False
                elif conn_res.status == "NOT_FOUND":
                    outcome = ObservationOutcome.ABSENT
                    is_live = True
                    observed_at = now
                else:
                    outcome = ObservationOutcome.OBSERVED
                    is_live = True
                    observed_at = now
            except Exception as exc:
                info = classify_aws_error(exc)
                outcome = outcome_from_aws_error(info)
                error = str(exc)
                is_live = False
        if git_sync_status is not None:
            remote_sync = RemoteSyncStatus.from_git_sync(git_sync_status)
    elif git_sync_status is not None:
        remote_sync = RemoteSyncStatus.from_git_sync(git_sync_status)

    return ConfigurationRepoSummary(
        repository_type=repo.type,
        target=resolved_target,
        local_git_branch=local_git_branch,
        local_git_clean=local_git_clean,
        local_git_uncommitted=local_git_uncommitted,
        git_sync_status=git_sync_status,
        remote_sync=remote_sync,
        is_live=is_live,
        outcome=outcome,
        observed_at=observed_at,
        last_attempt_at=last_attempt_at,
        error=error,
    )


def get_config_status_workflow(
    *,
    target_dir: Path | None = None,
    environment_target: CustomerEnvironmentTarget | None = None,
    config: WorkspaceConfig | None = None,
    state: WorkspaceState | None = None,
    workspace_dir: Path | None = None,
    config_dir: Path | None = None,
    aws_context: AwsExecutionContext | None = None,
) -> ConfigurationStatusResult:
    """Query workspace configuration and remote/pipeline status data."""
    if config is not None:
        resolved_workspace_dir = workspace_dir
        resolved_config = config
        resolved_target = environment_target or config.environment_target
        resolved_state = state
        resolved_config_dir = config_dir or (
            resolved_workspace_dir / resolved_config.configuration.local_path
            if resolved_workspace_dir is not None
            else None
        )
    elif environment_target is not None:
        resolved_workspace_dir = workspace_dir
        resolved_config = None
        resolved_target = environment_target
        resolved_state = state
        resolved_config_dir = config_dir
    else:
        ctx = load_workspace_context(
            target_dir, required_capabilities=(WorkspaceCapability.METADATA_VALID,)
        )
        resolved_workspace_dir = ctx.workspace_dir
        resolved_config = ctx.config
        resolved_target = ctx.environment_target
        resolved_state = ctx.state
        resolved_config_dir = config_dir or ctx.config_dir

    config_dir_exists = bool(resolved_config_dir and resolved_config_dir.exists())
    yaml_files = (
        tuple(
            sorted(
                file.name
                for file in resolved_config_dir.iterdir()
                if file.is_file() and file.suffix in (".yaml", ".yml")
            )
        )
        if resolved_config_dir is not None and config_dir_exists
        else ()
    )
    repo = resolved_target.configuration_repository

    profile = (
        (resolved_config.aws.profile or "")
        if resolved_config is not None
        else (aws_context.factory.profile or "" if aws_context is not None else "")
    )
    if aws_context is not None:
        resolved_aws = aws_context
    elif resolved_config is not None:
        resolved_aws = resolve_aws_execution_context(
            profile=profile,
            region=resolved_config.aws.region,
            role_arn=resolved_config.aws.role_arn,
            expected_account_id=resolved_config.aws.account_id,
            prime_credentials=resolved_config.aws.prime_credentials,
        )
    else:
        resolved_aws = resolve_aws_execution_context(
            region=resolved_target.region,
            expected_account_id=resolved_target.account_id,
        )
    factory = resolved_aws.factory
    region = resolved_aws.region
    aws_identity = resolved_aws.identity
    aws_error = resolved_aws.error
    account_id = aws_identity["account"] if aws_identity else "UNKNOWN_ACCOUNT"

    tmpl_state = resolved_state.configuration.template if resolved_state else None
    initialized_at = tmpl_state.initialized_at if tmpl_state else None
    template_name = tmpl_state.template_name if tmpl_state else None
    template_source = tmpl_state.template_source if tmpl_state else None
    drifted_fields: tuple[str, ...] = ()
    has_init_state = bool(
        resolved_config is not None
        and tmpl_state
        and tmpl_state.initialized_at
        and tmpl_state.init_values
    )
    if (
        has_init_state
        and resolved_config is not None
        and tmpl_state
        and tmpl_state.init_values
    ):
        current_snapshot = capture_init_values_snapshot(resolved_config)
        saved_snapshot = tmpl_state.init_values
        drifted_fields = tuple(
            sorted(k for k, v in current_snapshot.items() if saved_snapshot.get(k) != v)
        )

    # Git working tree and remote synchronization
    git_working_tree = (
        get_git_working_tree_status(resolved_config_dir)
        if resolved_config_dir is not None
        else None
    )
    git_sync_status = (
        get_git_remote_sync_status(resolved_config_dir, branch=repo.branch)
        if resolved_config_dir is not None and git_working_tree
        else None
    )

    workspace = ConfigurationWorkspaceStatus(
        workspace_dir=resolved_workspace_dir,
        customer_name=resolved_target.customer.name,
        lza_version=resolved_target.lza.version,
        profile=profile,
        region=region,
        aws_identity=aws_identity,
        aws_error=aws_error,
        config_dir=resolved_config_dir,
        config_dir_exists=config_dir_exists,
        yaml_files=yaml_files,
        initialized_at=initialized_at,
        template_name=template_name,
        template_source=template_source,
        drifted_fields=drifted_fields,
    )
    local_git = LocalGitStatus(working_tree=git_working_tree, sync_status=git_sync_status)

    repository, remote_sync = inspect_configuration_repository(
        repo=repo,
        config_dir=resolved_config_dir,
        environment_target=resolved_target,
        resolved_config=resolved_config,
        resolved_state=resolved_state,
        aws_identity=aws_identity,
        region=region,
        factory=factory,
        git_sync_status=git_sync_status,
    )

    pipeline = inspect_configuration_pipeline(
        environment_target=resolved_target,
        resolved_config=resolved_config,
        resolved_state=resolved_state,
        aws_identity=aws_identity,
        region=region,
        account_id=account_id,
        factory=factory,
    )

    recorded_pipeline_execution_id = (
        resolved_state.pipelines.configuration.latest_known_execution_id
        if resolved_state
        else None
    )
    last_push = resolved_state.configuration.last_push if resolved_state else None
    last_pull = resolved_state.configuration.last_pull if resolved_state else None
    sync_baseline = resolved_state.configuration.sync if resolved_state else None
    synchronization = ConfigurationSynchronizationStatus(
        has_state=resolved_state is not None,
        recorded_pipeline_execution_id=recorded_pipeline_execution_id,
        uploaded_at=last_push.recorded_at if last_push else None,
        downloaded_at=last_pull.recorded_at if last_pull else None,
        artifact_etag=sync_baseline.artifact_etag if sync_baseline else None,
        artifact_version_id=sync_baseline.artifact_version_id if sync_baseline else None,
        remote_sync=remote_sync,
    )

    warnings = compile_configuration_warnings(
        workspace=workspace,
        local_git=local_git,
        repository=repository,
        pipeline=pipeline,
    )
    return ConfigurationStatusResult(
        workspace=workspace,
        local_git=local_git,
        repository=repository,
        pipeline=pipeline,
        synchronization=synchronization,
        warnings=warnings,
    )


__all__ = [
    "CodeCommitConfigurationRepositoryStatus",
    "CodeConnectionConfigurationRepositoryStatus",
    "ConfigurationPipelineActionFailure",
    "ConfigurationPipelineStatus",
    "ConfigurationRepoSummary",
    "ConfigurationRepositoryStatus",
    "ConfigurationStatusResult",
    "ConfigurationSynchronizationStatus",
    "ConfigurationWorkspaceStatus",
    "GitConfigurationRepositoryStatus",
    "LocalGitStatus",
    "S3ConfigurationRepositoryStatus",
    "compile_configuration_warnings",
    "get_config_status_workflow",
    "observe_configuration_repository",
]
