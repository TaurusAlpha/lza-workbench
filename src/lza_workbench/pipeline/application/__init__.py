"""Pipeline application use cases."""

from lza_workbench.pipeline.application.start import (
    PipelineStartResult,
    start_pipeline_workflow,
)
from lza_workbench.pipeline.application.status import (
    PipelineSnapshotResult,
    get_pipeline_diagnostics_workflow,
    get_pipeline_snapshot_workflow,
)
from lza_workbench.pipeline.watcher import (
    PipelineWatchResult,
    PipelineWatchUpdate,
    watch_pipeline_workflow,
)

# Alias
snapshot_pipeline_workflow = get_pipeline_snapshot_workflow

__all__ = [
    "PipelineSnapshotResult",
    "PipelineStartResult",
    "PipelineWatchResult",
    "PipelineWatchUpdate",
    "get_pipeline_diagnostics_workflow",
    "get_pipeline_snapshot_workflow",
    "snapshot_pipeline_workflow",
    "start_pipeline_workflow",
    "watch_pipeline_workflow",
]
