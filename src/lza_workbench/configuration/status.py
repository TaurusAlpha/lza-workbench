"""Configuration status interpretation and remediation rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from lza_workbench.aws.codepipeline import PipelineStateResult
from lza_workbench.configuration.git import GitRemoteSyncStatus, GitWorkingTreeStatus
from lza_workbench.configuration.sync import RemoteSyncStatus


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
]
