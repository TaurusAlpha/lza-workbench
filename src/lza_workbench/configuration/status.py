"""Configuration status interpretation, inspection, and remediation rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from lza_workbench.configuration.git import (
    GitRemoteSyncStatus,
    GitWorkingTreeStatus,
    get_git_remote_sync_status,
    get_git_working_tree_status,
)
from lza_workbench.configuration.rendering import capture_init_values_snapshot
from lza_workbench.configuration.repository import (
    CONFIG_S3_OBJECT_KEY,
    resolve_s3_configuration_destination,
)
from lza_workbench.configuration.sync import (
    RemoteSyncStatus,
    evaluate_s3_remote_sync,
)
from lza_workbench.infrastructure.aws.codecommit import inspect_codecommit_repository
from lza_workbench.infrastructure.aws.codeconnections import inspect_codeconnection
from lza_workbench.infrastructure.aws.codepipeline import PipelineStateResult, get_pipeline_state
from lza_workbench.infrastructure.aws.s3 import (
    S3ObjectObservation,
    inspect_s3_bucket,
    inspect_s3_object_safe,
)
from lza_workbench.infrastructure.aws.session import resolve_aws_execution_context
from lza_workbench.pipeline.failures import (
    collect_pipeline_action_failures,
    fetch_codebuild_diagnostics,
)
from lza_workbench.workspace.context import WorkspaceCapability, load_workspace_context
from lza_workbench.workspace.schema import WorkspaceConfig, WorkspaceState


@dataclass(frozen=True)
class ConfigurationWorkspaceStatus:
    """Workspace and local configuration observations."""

    workspace_dir: Path
    customer_name: str
    lza_version: str
    profile: str
    region: str
    aws_identity: dict[str, str] | None
    aws_error: str | None
    config_dir: Path
    config_dir_exists: bool
    yaml_files: tuple[str, ...]
    initialized_at: datetime | None
    template_name: str | None
    template_source: str | None
    drifted_fields: tuple[str, ...]


@dataclass(frozen=True)
class LocalGitStatus:
    """Local configuration Git observations."""

    working_tree: GitWorkingTreeStatus | None
    sync_status: GitRemoteSyncStatus | None


@dataclass(frozen=True)
class S3ConfigurationRepositoryStatus:
    """S3 configuration archive observations."""

    bucket: str | None
    object_key: str
    bucket_exists: bool | None
    bucket_accessible: bool | None
    bucket_versioning: bool | None
    bucket_encryption: bool | None
    object_exists: bool | None
    object_etag: str | None
    object_version_id: str | None
    object_last_modified: datetime | None
    object_size: int | None
    error: str | None


@dataclass(frozen=True)
class CodeCommitConfigurationRepositoryStatus:
    """CodeCommit configuration repository observations."""

    repository_name: str
    branch_name: str
    exists: bool | None
    accessible: bool | None
    branch_exists: bool | None
    error: str | None


@dataclass(frozen=True)
class CodeConnectionConfigurationRepositoryStatus:
    """CodeConnection-backed configuration repository observations."""

    connection_arn: str | None
    owner: str | None
    repository_name: str | None
    branch_name: str | None
    status: str | None
    provider: str | None
    owner_account: str | None
    error: str | None


@dataclass(frozen=True)
class GitConfigurationRepositoryStatus:
    """Plain Git configuration repository settings."""

    repository_url: str | None
    repository_name: str | None
    branch_name: str | None


ConfigurationRepositoryStatus = (
    S3ConfigurationRepositoryStatus
    | CodeCommitConfigurationRepositoryStatus
    | CodeConnectionConfigurationRepositoryStatus
    | GitConfigurationRepositoryStatus
)


@dataclass(frozen=True)
class ConfigurationPipelineStatus:
    """Configuration pipeline observation, live when AWS is available."""

    name: str
    arn: str
    status: str | None
    execution_id: str | None
    failed_stage: str | None
    failed_action: str | None
    failed_build_url: str | None
    error: str | None
    state: PipelineStateResult | None


@dataclass(frozen=True)
class ConfigurationSynchronizationStatus:
    """Persisted configuration synchronization metadata."""

    has_state: bool
    recorded_pipeline_execution_id: str | None
    uploaded_at: datetime | None
    downloaded_at: datetime | None
    artifact_etag: str | None
    artifact_version_id: str | None
    remote_sync: RemoteSyncStatus | None


@dataclass(frozen=True)
class ConfigurationStatusResult:
    """Composed configuration-source status for interfaces to render."""

    workspace: ConfigurationWorkspaceStatus
    local_git: LocalGitStatus
    repository: ConfigurationRepositoryStatus
    pipeline: ConfigurationPipelineStatus
    synchronization: ConfigurationSynchronizationStatus
    warnings: tuple[str, ...]


def _compile_workspace_warnings(workspace: ConfigurationWorkspaceStatus) -> list[str]:
    """Compile warnings from local workspace observations."""
    warnings: list[str] = []
    if not workspace.config_dir_exists:
        warnings.append(
            "Local configuration directory is missing. "
            "Run 'lza config init' or 'lza config pull' to initialize it."
        )
    if workspace.drifted_fields:
        warnings.append(
            "Workspace settings changed since template initialization "
            f"({', '.join(workspace.drifted_fields)}). "
            "Run 'lza config init --force' to re-apply the template."
        )
    return warnings


def _compile_local_git_warnings(local_git: LocalGitStatus) -> list[str]:
    """Compile warnings from local Git observations."""
    warnings: list[str] = []
    if local_git.working_tree and local_git.working_tree.has_uncommitted:
        warnings.append(
            f"Local configuration contains {local_git.working_tree.uncommitted_count} uncommitted "
            "change(s). Commit or stash your changes before pushing."
        )
    if local_git.sync_status and local_git.sync_status.status == "Behind":
        warnings.append(
            f"Local configuration is behind remote repository by {local_git.sync_status.behind} "
            "commit(s). Run 'lza config pull' to synchronize."
        )
    elif local_git.sync_status and local_git.sync_status.status == "Diverged":
        warnings.append(
            f"Local configuration has diverged from remote ({local_git.sync_status.ahead} ahead, "
            f"{local_git.sync_status.behind} behind). Reconcile Git history before pushing."
        )
    return warnings


def _compile_s3_repository_warnings(repository: S3ConfigurationRepositoryStatus) -> list[str]:
    """Compile warnings from an S3 configuration repository."""
    label = f" '{repository.bucket}'" if repository.bucket else ""
    if repository.bucket_exists is False:
        return [f"Configured S3 bucket{label} does not exist."]
    if repository.bucket_accessible is False:
        return [f"Access denied or connection failure to configured S3 bucket{label}."]
    if repository.bucket_exists is True and repository.object_exists is False:
        return [
            f"Configuration archive is not present in S3 bucket{label}. "
            "Run 'lza config push' to upload local configuration."
        ]
    return []


def _compile_codecommit_repository_warnings(
    repository: CodeCommitConfigurationRepositoryStatus,
) -> list[str]:
    """Compile warnings from a CodeCommit configuration repository."""
    if repository.exists is False:
        return ["Configured CodeCommit repository does not exist."]
    if repository.accessible is False:
        return ["Access denied or connection failure to CodeCommit repository."]
    if repository.exists is True and repository.branch_exists is False:
        return [
            "Configured branch does not exist in CodeCommit repository. "
            "Run 'lza config push' to push branch."
        ]
    return []


def _compile_codeconnection_repository_warnings(
    repository: CodeConnectionConfigurationRepositoryStatus,
) -> list[str]:
    """Compile warnings from a CodeConnection configuration repository."""
    if repository.status == "PENDING":
        return ["CodeConnection is in PENDING status. Complete the handshake in the AWS Console."]
    if repository.status in {"ERROR", "NOT_FOUND", "INACCESSIBLE"}:
        return [f"CodeConnection issue detected (Status: {repository.status})."]
    return []


def _compile_repository_warnings(repository: ConfigurationRepositoryStatus) -> list[str]:
    """Compile warnings from the configured remote repository."""
    if isinstance(repository, S3ConfigurationRepositoryStatus):
        return _compile_s3_repository_warnings(repository)
    if isinstance(repository, CodeCommitConfigurationRepositoryStatus):
        return _compile_codecommit_repository_warnings(repository)
    if isinstance(repository, CodeConnectionConfigurationRepositoryStatus):
        return _compile_codeconnection_repository_warnings(repository)
    return []


def _compile_pipeline_warnings(pipeline: ConfigurationPipelineStatus) -> list[str]:
    """Compile warnings from the latest configuration pipeline execution."""
    if pipeline.status == "Failed":
        detail = (
            f" (Stage: '{pipeline.failed_stage}', Action: '{pipeline.failed_action}')"
            if pipeline.failed_stage and pipeline.failed_action
            else f" (Stage: '{pipeline.failed_stage}')"
            if pipeline.failed_stage
            else ""
        )
        return [f"Latest execution of configuration pipeline '{pipeline.name}' failed{detail}."]
    if pipeline.status == "Cancelled":
        return [f"Latest execution of configuration pipeline '{pipeline.name}' was cancelled."]
    return []


def compile_configuration_warnings(
    *,
    workspace: ConfigurationWorkspaceStatus,
    local_git: LocalGitStatus,
    repository: ConfigurationRepositoryStatus,
    pipeline: ConfigurationPipelineStatus,
) -> tuple[str, ...]:
    """Interpret configuration observations into actionable warnings."""
    warnings = _compile_workspace_warnings(workspace)
    warnings.extend(_compile_local_git_warnings(local_git))
    warnings.extend(_compile_repository_warnings(repository))
    warnings.extend(_compile_pipeline_warnings(pipeline))
    return tuple(warnings)


def _inspect_s3_repository_status(
    *,
    repo: Any,
    config_dir: Path,
    resolved_config: WorkspaceConfig,
    resolved_state: WorkspaceState | None,
    aws_identity: dict[str, Any] | None,
    region: str,
    factory: Any,
) -> tuple[S3ConfigurationRepositoryStatus, RemoteSyncStatus]:
    s3_bucket_name = None
    s3_error = None
    try:
        s3_bucket_name = resolve_s3_configuration_destination(
            configured_bucket=repo.bucket,
            account_id=(
                resolved_config.aws.account_id
                or (resolved_state.management_account_id if resolved_state else None)
                or (aws_identity.get("account") if aws_identity else None)
            ),
            region=region or resolved_config.aws.region,
        ).bucket
    except Exception as exc:
        s3_error = str(exc)

    s3_bucket_exists = None
    s3_bucket_accessible = None
    s3_bucket_versioning = None
    s3_bucket_encryption = None
    s3_object_exists = None
    s3_object_etag = None
    s3_object_version_id = None
    s3_object_last_modified = None
    s3_object_size = None
    obj_info: S3ObjectObservation | None = None

    if s3_bucket_name and aws_identity:
        try:
            s3_client = factory.get_client("s3")
            b_info = inspect_s3_bucket(client=s3_client, bucket_name=s3_bucket_name)
            s3_bucket_exists = b_info.exists
            s3_bucket_accessible = b_info.accessible
            s3_bucket_versioning = b_info.versioning_enabled
            s3_bucket_encryption = b_info.encryption_enabled

            if s3_bucket_exists:
                obj_info = inspect_s3_object_safe(
                    client=s3_client,
                    bucket_name=s3_bucket_name,
                    object_key=CONFIG_S3_OBJECT_KEY,
                )
                s3_object_exists = obj_info.exists
                s3_object_etag = obj_info.etag
                s3_object_version_id = obj_info.version_id
                s3_object_last_modified = obj_info.last_modified
                s3_object_size = obj_info.content_length
        except Exception as exc:
            s3_error = str(exc)
            s3_bucket_accessible = False

    remote_sync = evaluate_s3_remote_sync(
        config_dir=config_dir,
        exclude_dirs=set(resolved_config.configuration.packaging.exclude.directories),
        exclude_files=set(resolved_config.configuration.packaging.exclude.files),
        s3_object_info=obj_info,
        state=resolved_state,
        is_live=bool(aws_identity),
    )

    repository = S3ConfigurationRepositoryStatus(
        bucket=s3_bucket_name,
        object_key=CONFIG_S3_OBJECT_KEY,
        bucket_exists=s3_bucket_exists,
        bucket_accessible=s3_bucket_accessible,
        bucket_versioning=s3_bucket_versioning,
        bucket_encryption=s3_bucket_encryption,
        object_exists=s3_object_exists,
        object_etag=s3_object_etag,
        object_version_id=s3_object_version_id,
        object_last_modified=s3_object_last_modified,
        object_size=s3_object_size,
        error=s3_error,
    )
    return repository, remote_sync


def _inspect_codecommit_repository_status(
    *,
    repo: Any,
    aws_identity: dict[str, Any] | None,
    factory: Any,
) -> CodeCommitConfigurationRepositoryStatus:
    repo_name = repo.repository_name or "aws-accelerator-config"
    branch_name = repo.branch or "main"
    codecommit_exists = None
    codecommit_accessible = None
    codecommit_branch_exists = None
    codecommit_error = None

    if aws_identity:
        try:
            cc_client = factory.get_client("codecommit")
            cc_info = inspect_codecommit_repository(
                client=cc_client, repository_name=repo_name, branch_name=branch_name
            )
            codecommit_exists = cc_info.exists
            codecommit_accessible = cc_info.accessible
            codecommit_branch_exists = cc_info.branch_exists
            codecommit_error = cc_info.error
        except Exception as exc:
            codecommit_error = str(exc)
            codecommit_accessible = False

    return CodeCommitConfigurationRepositoryStatus(
        repository_name=repo_name,
        branch_name=branch_name,
        exists=codecommit_exists,
        accessible=codecommit_accessible,
        branch_exists=codecommit_branch_exists,
        error=codecommit_error,
    )


def _inspect_codeconnection_repository_status(
    *,
    repo: Any,
    aws_identity: dict[str, Any] | None,
    factory: Any,
) -> CodeConnectionConfigurationRepositoryStatus:
    codeconnection_status = None
    codeconnection_provider = None
    codeconnection_owner_account = None
    codeconnection_error = None

    if repo.codeconnection_arn and aws_identity:
        conn_client = factory.get_client("codeconnections")
        conn_res = inspect_codeconnection(
            client=conn_client,
            connection_arn=repo.codeconnection_arn,
        )
        codeconnection_status = conn_res.status
        codeconnection_provider = conn_res.provider_type
        codeconnection_owner_account = conn_res.owner_account_id
        codeconnection_error = conn_res.error

    return CodeConnectionConfigurationRepositoryStatus(
        connection_arn=repo.codeconnection_arn,
        owner=repo.owner,
        repository_name=repo.repository_name,
        branch_name=repo.branch,
        status=codeconnection_status,
        provider=codeconnection_provider,
        owner_account=codeconnection_owner_account,
        error=codeconnection_error,
    )


def _inspect_configuration_repository(
    *,
    repo: Any,
    config_dir: Path,
    resolved_config: WorkspaceConfig,
    resolved_state: WorkspaceState | None,
    aws_identity: dict[str, Any] | None,
    region: str,
    factory: Any,
    git_sync_status: Any,
) -> tuple[ConfigurationRepositoryStatus, RemoteSyncStatus | None]:
    if repo.type == "s3":
        return _inspect_s3_repository_status(
            repo=repo,
            config_dir=config_dir,
            resolved_config=resolved_config,
            resolved_state=resolved_state,
            aws_identity=aws_identity,
            region=region,
            factory=factory,
        )

    remote_sync = (
        RemoteSyncStatus.from_git_sync(git_sync_status) if git_sync_status is not None else None
    )

    if repo.type == "codecommit":
        repository = _inspect_codecommit_repository_status(
            repo=repo,
            aws_identity=aws_identity,
            factory=factory,
        )
    elif repo.type == "codeconnection":
        repository = _inspect_codeconnection_repository_status(
            repo=repo,
            aws_identity=aws_identity,
            factory=factory,
        )
    else:
        repository = GitConfigurationRepositoryStatus(
            repository_url=repo.repository,
            repository_name=repo.repository_name,
            branch_name=repo.branch,
        )

    return repository, remote_sync


def _inspect_configuration_pipeline(
    *,
    resolved_config: WorkspaceConfig,
    resolved_state: WorkspaceState | None,
    aws_identity: dict[str, Any] | None,
    region: str,
    account_id: str,
    factory: Any,
) -> ConfigurationPipelineStatus:
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


def get_config_status_workflow(
    *,
    target_dir: Path | None = None,
    config: WorkspaceConfig | None = None,
    state: WorkspaceState | None = None,
    workspace_dir: Path | None = None,
) -> ConfigurationStatusResult:
    """Query workspace configuration and remote/pipeline status data."""
    if config is not None and workspace_dir is not None:
        resolved_workspace_dir = workspace_dir
        resolved_config = config
        resolved_state = state
        config_dir = resolved_workspace_dir / resolved_config.configuration.local_path
    else:
        ctx = load_workspace_context(
            target_dir, required_capabilities=(WorkspaceCapability.METADATA_VALID,)
        )
        resolved_workspace_dir = ctx.workspace_dir
        resolved_config = ctx.config
        resolved_state = ctx.state
        config_dir = ctx.config_dir
    yaml_files = (
        tuple(
            sorted(
                file.name
                for file in config_dir.iterdir()
                if file.is_file() and file.suffix in (".yaml", ".yml")
            )
        )
        if config_dir.exists()
        else ()
    )
    repo = resolved_config.configuration.repository

    profile = resolved_config.aws.profile or ""
    aws_context = resolve_aws_execution_context(
        profile=profile,
        region=resolved_config.aws.region,
        role_arn=resolved_config.aws.role_arn,
        expected_account_id=resolved_config.aws.account_id,
        prime_credentials=resolved_config.aws.prime_credentials,
    )
    factory = aws_context.factory
    region = aws_context.region
    aws_identity = aws_context.identity
    aws_error = aws_context.error
    account_id = aws_identity["account"] if aws_identity else "UNKNOWN_ACCOUNT"

    initialized_at = resolved_state.config_initialized_at if resolved_state else None
    template_name = resolved_state.config_template_name if resolved_state else None
    template_source = resolved_state.config_template_source if resolved_state else None
    drifted_fields: tuple[str, ...] = ()
    has_init_state = bool(
        resolved_state
        and resolved_state.config_initialized_at
        and resolved_state.config_init_values
    )
    if has_init_state and resolved_state and resolved_state.config_init_values:
        current_snapshot = capture_init_values_snapshot(resolved_config)
        saved_snapshot = resolved_state.config_init_values
        drifted_fields = tuple(
            sorted(k for k, v in current_snapshot.items() if saved_snapshot.get(k) != v)
        )

    # Git working tree and remote synchronization
    git_working_tree = get_git_working_tree_status(config_dir)
    git_sync_status = (
        get_git_remote_sync_status(config_dir, branch=repo.branch) if git_working_tree else None
    )

    workspace = ConfigurationWorkspaceStatus(
        workspace_dir=resolved_workspace_dir,
        customer_name=resolved_config.customer.name,
        lza_version=resolved_config.lza.version,
        profile=profile,
        region=region,
        aws_identity=aws_identity,
        aws_error=aws_error,
        config_dir=config_dir,
        config_dir_exists=config_dir.exists(),
        yaml_files=yaml_files,
        initialized_at=initialized_at,
        template_name=template_name,
        template_source=template_source,
        drifted_fields=drifted_fields,
    )
    local_git = LocalGitStatus(working_tree=git_working_tree, sync_status=git_sync_status)

    repository, remote_sync = _inspect_configuration_repository(
        repo=repo,
        config_dir=config_dir,
        resolved_config=resolved_config,
        resolved_state=resolved_state,
        aws_identity=aws_identity,
        region=region,
        factory=factory,
        git_sync_status=git_sync_status,
    )

    pipeline = _inspect_configuration_pipeline(
        resolved_config=resolved_config,
        resolved_state=resolved_state,
        aws_identity=aws_identity,
        region=region,
        account_id=account_id,
        factory=factory,
    )

    recorded_pipeline_execution_id = (
        resolved_state.config_pipeline_execution_id if resolved_state else None
    )
    synchronization = ConfigurationSynchronizationStatus(
        has_state=resolved_state is not None,
        recorded_pipeline_execution_id=recorded_pipeline_execution_id,
        uploaded_at=resolved_state.config_uploaded_at if resolved_state else None,
        downloaded_at=resolved_state.config_downloaded_at if resolved_state else None,
        artifact_etag=resolved_state.config_artifact_etag if resolved_state else None,
        artifact_version_id=resolved_state.config_artifact_version_id if resolved_state else None,
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
    "ConfigurationPipelineStatus",
    "ConfigurationRepositoryStatus",
    "ConfigurationStatusResult",
    "ConfigurationSynchronizationStatus",
    "ConfigurationWorkspaceStatus",
    "GitConfigurationRepositoryStatus",
    "LocalGitStatus",
    "S3ConfigurationRepositoryStatus",
    "compile_configuration_warnings",
    "get_config_status_workflow",
]
