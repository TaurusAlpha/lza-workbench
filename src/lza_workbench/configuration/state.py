"""Configuration operational state models, synchronization baselines, and transfer records."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from lza_workbench.configuration.archive import (
    ConfigDiffResult,
    compute_config_directory_digest,
    compute_zip_content_digest,
    count_config_files,
    scan_zip_files,
)

if TYPE_CHECKING:
    from lza_workbench.workspace.schema import WorkspaceState


class ConfigurationTemplateState(BaseModel):
    """Local configuration template initialization provenance."""

    model_config = ConfigDict(extra="forbid", strict=False)

    initialized_at: datetime | None = None
    template_name: str | None = None
    template_source: str | None = None
    init_values: dict[str, str] | None = None
    init_digest: str | None = None


class ConfigurationSyncBaseline(BaseModel):
    """Local checkout synchronization baseline against the customer configuration repository."""

    model_config = ConfigDict(extra="forbid", strict=False)

    sync_digest: str | None = None
    artifact_etag: str | None = None
    artifact_version_id: str | None = None
    commit_sha: str | None = None
    files_count: int | None = None
    verified_at: datetime | None = None


class ConfigurationTransferRecord(BaseModel):
    """Recorded outcome of a configuration push or pull operation."""

    model_config = ConfigDict(extra="forbid", strict=False)

    direction: Literal["push", "pull"]
    repository_type: str
    recorded_at: datetime
    archive_sha256: str | None = None
    artifact_etag: str | None = None
    artifact_version_id: str | None = None
    commit_sha: str | None = None
    files_count: int | None = None
    diff_summary: dict[str, int] | None = None


class ConfigurationState(BaseModel):
    """Persisted configuration template provenance, sync baseline, and transfer history."""

    model_config = ConfigDict(extra="forbid", strict=False)

    template: ConfigurationTemplateState = Field(default_factory=ConfigurationTemplateState)
    sync: ConfigurationSyncBaseline = Field(default_factory=ConfigurationSyncBaseline)
    last_push: ConfigurationTransferRecord | None = None
    last_pull: ConfigurationTransferRecord | None = None


def record_config_template_init(
    state: WorkspaceState,
    *,
    template_name: str,
    template_source: str,
    init_values: dict[str, str],
    init_digest: str,
    files_count: int,
) -> None:
    """Record local configuration template rendering provenance."""
    now = datetime.now(UTC)
    state.configuration.template = ConfigurationTemplateState(
        initialized_at=now,
        template_name=template_name,
        template_source=template_source,
        init_values=dict(init_values),
        init_digest=init_digest,
    )
    state.configuration.sync.files_count = files_count
    state.touch(now)


def record_config_upload(
    state: WorkspaceState,
    *,
    zip_path: Path,
    config_dir: Path,
    manifest: dict[str, tuple[int, int]],
    exclude_dirs: set[str],
    exclude_files: set[str],
    diff_result: ConfigDiffResult,
    etag: str | None,
    version_id: str | None,
    sync_digest: str | None = None,
    archive_sha256: str | None = None,
) -> None:
    """Record synchronization baseline and transfer record after an S3 archive upload."""
    now = datetime.now(UTC)
    archive_sha = archive_sha256 or _archive_sha256(zip_path)
    files_count = len(manifest)
    resolved_sync_digest = sync_digest or (
        compute_zip_content_digest(zip_path, exclude_dirs, exclude_files)
        if zip_path.is_file()
        else compute_config_directory_digest(config_dir, exclude_dirs, exclude_files)
    )
    summary = _diff_summary(diff_result)

    state.configuration.sync.sync_digest = resolved_sync_digest
    state.configuration.sync.artifact_etag = etag
    state.configuration.sync.artifact_version_id = version_id
    state.configuration.sync.files_count = files_count
    state.configuration.sync.verified_at = now
    state.configuration.last_push = ConfigurationTransferRecord(
        direction="push",
        repository_type="s3",
        recorded_at=now,
        archive_sha256=archive_sha,
        artifact_etag=etag,
        artifact_version_id=version_id,
        files_count=files_count,
        diff_summary=summary,
    )
    state.touch(now)


def record_config_download(
    state: WorkspaceState,
    *,
    zip_path: Path,
    config_dir: Path,
    exclude_dirs: set[str],
    exclude_files: set[str],
    diff_result: ConfigDiffResult,
    extracted: bool,
    etag: str | None = None,
    version_id: str | None = None,
    sync_digest: str | None = None,
    files_count: int | None = None,
    archive_sha256: str | None = None,
) -> None:
    """Record synchronization baseline and transfer record after an S3 archive download."""
    now = datetime.now(UTC)
    archive_sha = archive_sha256 or (_archive_sha256(zip_path) if zip_path.exists() else None)
    summary = _diff_summary(diff_result)

    if etag:
        state.configuration.sync.artifact_etag = etag
    if version_id:
        state.configuration.sync.artifact_version_id = version_id

    resolved_files_count: int | None = files_count
    if extracted:
        if zip_path.is_file():
            zip_files = scan_zip_files(
                zip_path,
                exclude_dirs,
                exclude_files,
                top_level_dir_name=config_dir.name,
            )
            if resolved_files_count is None:
                resolved_files_count = len(zip_files)
            resolved_digest = sync_digest or compute_zip_content_digest(
                zip_path,
                exclude_dirs,
                exclude_files,
                top_level_dir_name=config_dir.name,
            )
        elif config_dir.exists():
            if resolved_files_count is None:
                resolved_files_count = count_config_files(config_dir, exclude_dirs, exclude_files)
            resolved_digest = sync_digest or compute_config_directory_digest(
                config_dir, exclude_dirs, exclude_files
            )
        else:
            resolved_digest = sync_digest

        if resolved_digest is not None:
            state.configuration.sync.files_count = resolved_files_count
            state.configuration.sync.sync_digest = resolved_digest
            state.configuration.sync.verified_at = now
    else:
        state.configuration.sync.sync_digest = None

    state.configuration.last_pull = ConfigurationTransferRecord(
        direction="pull",
        repository_type="s3",
        recorded_at=now,
        archive_sha256=archive_sha,
        artifact_etag=etag or state.configuration.sync.artifact_etag,
        artifact_version_id=version_id or state.configuration.sync.artifact_version_id,
        files_count=resolved_files_count,
        diff_summary=summary,
    )
    state.touch(now)


def cache_verified_s3_sync(
    state: WorkspaceState,
    *,
    etag: str | None,
    version_id: str | None,
    digest: str,
) -> None:
    """Record verified S3 archive synchronization baseline metadata."""
    now = datetime.now(UTC)
    state.configuration.sync.artifact_etag = etag
    state.configuration.sync.artifact_version_id = version_id
    state.configuration.sync.sync_digest = digest
    state.configuration.sync.verified_at = now
    state.touch(now)


def record_config_git_push(
    state: WorkspaceState,
    *,
    files_count: int,
    commit_hash: str | None = None,
    repository_type: str = "git",
) -> None:
    """Record synchronization baseline and transfer outcome after a Git configuration push."""
    now = datetime.now(UTC)
    state.configuration.sync.files_count = files_count
    if commit_hash:
        state.configuration.sync.commit_sha = commit_hash
    state.configuration.sync.verified_at = now
    state.configuration.last_push = ConfigurationTransferRecord(
        direction="push",
        repository_type=repository_type,
        recorded_at=now,
        commit_sha=commit_hash,
        files_count=files_count,
    )
    state.touch(now)


def record_config_git_pull(
    state: WorkspaceState,
    *,
    files_count: int,
    commit_hash: str | None = None,
    repository_type: str = "git",
) -> None:
    """Record synchronization baseline and transfer outcome after a Git configuration pull."""
    now = datetime.now(UTC)
    state.configuration.sync.files_count = files_count
    if commit_hash:
        state.configuration.sync.commit_sha = commit_hash
    state.configuration.sync.verified_at = now
    state.configuration.last_pull = ConfigurationTransferRecord(
        direction="pull",
        repository_type=repository_type,
        recorded_at=now,
        commit_sha=commit_hash,
        files_count=files_count,
    )
    state.touch(now)


def _archive_sha256(zip_path: Path) -> str:
    return hashlib.sha256(zip_path.read_bytes()).hexdigest()


def _diff_summary(diff_result: ConfigDiffResult) -> dict[str, int]:
    return {
        "added": len(diff_result.added),
        "modified": len(diff_result.modified),
        "removed": len(diff_result.removed),
    }


__all__ = [
    "ConfigurationState",
    "ConfigurationSyncBaseline",
    "ConfigurationTemplateState",
    "ConfigurationTransferRecord",
    "cache_verified_s3_sync",
    "record_config_download",
    "record_config_git_pull",
    "record_config_git_push",
    "record_config_template_init",
    "record_config_upload",
]
