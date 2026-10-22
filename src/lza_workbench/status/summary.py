"""Summary presentation models for root status reporting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from lza_workbench.configuration.status import ConfigurationRepoSummary
from lza_workbench.installer.status import InstallerStackSummary
from lza_workbench.pipeline.model import PipelineSummary

if TYPE_CHECKING:
    from lza_workbench.workspace.validation import WorkspaceAssessment


@dataclass(frozen=True)
class OverallHealthSummary:
    installer: str
    configuration: str
    workspace: str
    is_live: bool = True


@dataclass(frozen=True)
class RootStatusResult:
    workspace_dir: Path | None
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
    observed_at: datetime | None = None
    last_attempt_at: datetime | None = None


__all__ = [
    "ConfigurationRepoSummary",
    "InstallerStackSummary",
    "OverallHealthSummary",
    "PipelineSummary",
    "RootStatusResult",
]
