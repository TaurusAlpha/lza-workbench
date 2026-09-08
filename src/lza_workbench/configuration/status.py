"""Configuration status interpretation and remediation rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from lza_workbench.aws.codepipeline import PipelineStateResult
from lza_workbench.configuration.git import GitRemoteSyncStatus, GitWorkingTreeStatus


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
    uploaded_at: object | None
    downloaded_at: object | None
    artifact_etag: str | None
    artifact_version_id: str | None


@dataclass(frozen=True)
class ConfigurationStatusResult:
    """Composed configuration-source status for interfaces to render."""

    workspace: ConfigurationWorkspaceStatus
    local_git: LocalGitStatus
    repository: ConfigurationRepositoryStatus
    pipeline: ConfigurationPipelineStatus
    synchronization: ConfigurationSynchronizationStatus
    warnings: tuple[str, ...]


def compile_configuration_warnings(
    *,
    workspace: ConfigurationWorkspaceStatus,
    local_git: LocalGitStatus,
    repository: ConfigurationRepositoryStatus,
    pipeline: ConfigurationPipelineStatus,
) -> tuple[str, ...]:
    """Interpret configuration observations into actionable warnings."""
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
    if isinstance(repository, S3ConfigurationRepositoryStatus):
        label = f" '{repository.bucket}'" if repository.bucket else ""
        if repository.bucket_exists is False:
            warnings.append(f"Configured S3 bucket{label} does not exist.")
        elif repository.bucket_accessible is False:
            warnings.append(f"Access denied or connection failure to configured S3 bucket{label}.")
        elif repository.bucket_exists is True and repository.object_exists is False:
            warnings.append(
                f"Configuration archive is not present in S3 bucket{label}. "
                "Run 'lza config push' to upload local configuration."
            )
    elif isinstance(repository, CodeCommitConfigurationRepositoryStatus):
        if repository.exists is False:
            warnings.append("Configured CodeCommit repository does not exist.")
        elif repository.accessible is False:
            warnings.append("Access denied or connection failure to CodeCommit repository.")
        elif repository.exists is True and repository.branch_exists is False:
            warnings.append(
                "Configured branch does not exist in CodeCommit repository. "
                "Run 'lza config push' to push branch."
            )
    elif isinstance(repository, CodeConnectionConfigurationRepositoryStatus):
        if repository.status == "PENDING":
            warnings.append(
                "CodeConnection is in PENDING status. Complete the handshake in the AWS Console."
            )
        elif repository.status in {"ERROR", "NOT_FOUND", "INACCESSIBLE"}:
            warnings.append(f"CodeConnection issue detected (Status: {repository.status}).")
    if pipeline.status == "Failed":
        detail = (
            f" (Stage: '{pipeline.failed_stage}', Action: '{pipeline.failed_action}')"
            if pipeline.failed_stage and pipeline.failed_action
            else f" (Stage: '{pipeline.failed_stage}')"
            if pipeline.failed_stage
            else ""
        )
        warnings.append(
            f"Latest execution of configuration pipeline '{pipeline.name}' failed{detail}."
        )
    elif pipeline.status == "Cancelled":
        warnings.append(
            f"Latest execution of configuration pipeline '{pipeline.name}' was cancelled."
        )
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
