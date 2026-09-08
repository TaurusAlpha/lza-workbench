"""Provider-neutral operational models for pipeline executions."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PipelineActionState:
    """Observed state of an action within a pipeline stage."""

    action_name: str
    stage_name: str | None = None
    status: str | None = None
    summary: str | None = None
    last_status_change: str | None = None
    error_message: str | None = None
    external_execution_id: str | None = None
    external_execution_url: str | None = None
    execution_id: str | None = None


@dataclass(frozen=True)
class PipelineStageState:
    """Observed state of a pipeline stage and its actions."""

    stage_name: str
    status: str | None = None
    actions: list[PipelineActionState] = field(default_factory=list)
    execution_id: str | None = None


@dataclass(frozen=True)
class PipelineExecutionSnapshot:
    """A single provider-neutral observation of a pipeline or execution."""

    pipeline_name: str
    exists: bool
    status: str | None = None
    execution_id: str | None = None
    stages: list[PipelineStageState] = field(default_factory=list)
    latest_execution_id: str | None = None
    status_summary: str | None = None
    start_time: str | None = None
    last_update_time: str | None = None
    duration_seconds: float | None = None
    created: str | None = None
    updated: str | None = None
    error: str | None = None


__all__ = [
    "PipelineActionState",
    "PipelineExecutionSnapshot",
    "PipelineStageState",
]
