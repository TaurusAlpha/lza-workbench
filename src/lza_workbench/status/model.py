"""Status domain models and snapshots."""

from __future__ import annotations

from lza_workbench.status.observer import (
    ConfigurationRepoSummary,
    InstallerStackSummary,
    OverallHealthSummary,
    PipelineSummary,
    RootStatusResult,
)

# Counterfactual aliases
WorkspaceSnapshot = RootStatusResult

__all__ = [
    "ConfigurationRepoSummary",
    "InstallerStackSummary",
    "OverallHealthSummary",
    "PipelineSummary",
    "RootStatusResult",
    "WorkspaceSnapshot",
]
