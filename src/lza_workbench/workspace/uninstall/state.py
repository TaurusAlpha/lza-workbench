"""Runtime state schema for LZA uninstallation."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RetainedResourceRecord(BaseModel):
    """Individual retained physical resource tracked in .lza/state.json."""

    model_config = ConfigDict(extra="forbid", strict=False)

    account_id: str
    region: str
    stack_name: str
    logical_id: str
    physical_id: str
    resource_type: str
    status: str = "retained"  # "retained", "deleted", "failed"
    error: str | None = None


class UninstallRuntimeState(BaseModel):
    """Operational uninstall state stored in .lza/state.json."""

    model_config = ConfigDict(extra="forbid", strict=False)

    uninstalled_at: datetime | None = None
    status: str | None = None  # "in_progress", "completed", "failed"
    deleted_stacks: list[str] = Field(default_factory=list)
    deleted_buckets: list[str] = Field(default_factory=list)
    retained_resources: list[RetainedResourceRecord] = Field(default_factory=list)


__all__ = [
    "RetainedResourceRecord",
    "UninstallRuntimeState",
]
