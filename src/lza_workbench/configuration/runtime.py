"""Runtime state owned by configuration synchronization actions."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConfigurationRuntimeState(BaseModel):
    """Operational metadata recorded for the customer configuration repository."""

    model_config = ConfigDict(extra="forbid", strict=False)

    initialized_at: datetime | None = None
    template_name: str | None = None
    template_source: str | None = None
    init_values: dict[str, str] | None = None
    init_digest: str | None = None
    uploaded_at: datetime | None = None
    downloaded_at: datetime | None = None
    artifact_etag: str | None = None
    artifact_version_id: str | None = None
    artifact_sha256: str | None = None
    sync_digest: str | None = None
    files_count: int | None = None
    last_diff_summary: dict[str, int] | None = None


__all__ = ["ConfigurationRuntimeState"]
