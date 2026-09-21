"""Runtime state owned by installer actions."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InstallerRuntimeState(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=False)

    stack_id: str | None = None
    stack_status: str | None = None
    stack_updated_at: datetime | None = None
    downloaded_at: datetime | None = None
    template_version: str | None = None
    template_digest: str | None = None
    deployed_parameters: dict[str, str] | None = None
    pending_parameters: dict[str, str] | None = None


__all__ = ["InstallerRuntimeState"]
