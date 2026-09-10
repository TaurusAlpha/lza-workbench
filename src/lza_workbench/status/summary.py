"""Summary presentation models for root status reporting."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from lza_workbench.configuration.git import GitRemoteSyncStatus
from lza_workbench.configuration.sync import RemoteSyncStatus

if TYPE_CHECKING:
    from lza_workbench.workspace.validation import WorkspaceAssessment


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


__all__ = [
    "ConfigurationRepoSummary",
    "InstallerStackSummary",
    "OverallHealthSummary",
    "PipelineSummary",
    "RootStatusResult",
]
