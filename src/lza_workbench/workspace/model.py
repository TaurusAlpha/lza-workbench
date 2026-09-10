"""Workspace domain and persistence models."""

from __future__ import annotations

from lza_workbench.workspace.schema import (
    AwsConfig,
    CliConfig,
    CustomerConfig,
    LzaConfig,
    PipelineConfig,
    PipelinesConfig,
    WorkspaceConfig,
    WorkspaceModel,
    WorkspaceState,
)

# Counterfactual aliases
WorkspaceDocument = WorkspaceConfig
WorkspaceRuntime = WorkspaceState

__all__ = [
    "AwsConfig",
    "CliConfig",
    "CustomerConfig",
    "LzaConfig",
    "PipelineConfig",
    "PipelinesConfig",
    "WorkspaceConfig",
    "WorkspaceDocument",
    "WorkspaceModel",
    "WorkspaceRuntime",
    "WorkspaceState",
]
