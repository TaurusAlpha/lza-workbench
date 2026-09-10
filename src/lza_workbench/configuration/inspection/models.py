"""Structured observation and status models for LZA configuration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from lza_workbench.configuration.git import (
    GitRemoteSyncStatus,
    GitWorkingTreeStatus,
)
from lza_workbench.configuration.sync import RemoteSyncStatus
from lza_workbench.infrastructure.aws.codepipeline import PipelineStateResult


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
    """CodeConnection repository observations."""

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
    """Generic Git repository observations."""

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
class ConfigurationPipelineActionFailure:
    """Diagnostic detail for a failed CodePipeline action."""

    stage_name: str
    action_name: str
    status: str | None
    summary: str | None
    error_message: str | None
    external_execution_id: str | None
    external_execution_url: str | None
    diagnostic_details: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConfigurationPipelineStatus:
    """Configuration pipeline observations."""

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


__all__ = [
    "CodeCommitConfigurationRepositoryStatus",
    "CodeConnectionConfigurationRepositoryStatus",
    "ConfigurationPipelineActionFailure",
    "ConfigurationPipelineStatus",
    "ConfigurationRepositoryStatus",
    "ConfigurationStatusResult",
    "ConfigurationSynchronizationStatus",
    "ConfigurationWorkspaceStatus",
    "GitConfigurationRepositoryStatus",
    "LocalGitStatus",
    "S3ConfigurationRepositoryStatus",
]
