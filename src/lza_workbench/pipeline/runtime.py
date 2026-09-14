"""Runtime state owned by pipeline execution actions."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PipelineExecutionRuntimeState(BaseModel):
    """Recorded execution and terminal diagnostic details for one pipeline."""

    model_config = ConfigDict(extra="forbid", strict=False)

    execution_id: str | None = None
    name: str | None = None
    status: str | None = None
    failed_stage: str | None = None
    failed_action: str | None = None
    failed_build_url: str | None = None
    error: str | None = None


class PipelinesRuntimeState(BaseModel):
    """Recorded execution details for installer and configuration pipelines."""

    model_config = ConfigDict(extra="forbid", strict=False)

    installer: PipelineExecutionRuntimeState = Field(default_factory=PipelineExecutionRuntimeState)
    configuration: PipelineExecutionRuntimeState = Field(
        default_factory=PipelineExecutionRuntimeState
    )


__all__ = ["PipelineExecutionRuntimeState", "PipelinesRuntimeState"]
