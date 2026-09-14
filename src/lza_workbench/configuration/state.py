"""Operational state updates for configuration archive transfers."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from lza_workbench.configuration.archive import (
    ConfigDiffResult,
    compute_config_directory_digest,
    count_config_files,
)
from lza_workbench.workspace.schema import WorkspaceState


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
) -> None:
    """Record metadata after a successful configuration archive upload."""
    now = datetime.now(UTC)
    state.updated_at = now
    state.configuration.uploaded_at = now
    state.configuration.artifact_sha256 = _archive_sha256(zip_path)
    state.configuration.artifact_etag = etag
    state.configuration.artifact_version_id = version_id
    state.configuration.files_count = len(manifest)
    state.configuration.sync_digest = compute_config_directory_digest(
        config_dir, exclude_dirs, exclude_files
    )
    state.configuration.last_diff_summary = _diff_summary(diff_result)


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
) -> None:
    """Record metadata after a successful configuration archive download."""
    now = datetime.now(UTC)
    state.updated_at = now
    state.configuration.downloaded_at = now
    if zip_path.exists():
        state.configuration.artifact_sha256 = _archive_sha256(zip_path)
    if etag:
        state.configuration.artifact_etag = etag
    if version_id:
        state.configuration.artifact_version_id = version_id
    if extracted and config_dir.exists():
        state.configuration.files_count = count_config_files(config_dir, exclude_dirs, exclude_files)
        state.configuration.sync_digest = compute_config_directory_digest(
            config_dir, exclude_dirs, exclude_files
        )
    elif not extracted:
        state.configuration.sync_digest = None
    state.configuration.last_diff_summary = _diff_summary(diff_result)


def cache_verified_s3_sync(
    state: WorkspaceState,
    *,
    etag: str | None,
    version_id: str | None,
    digest: str,
) -> None:
    """Record verified S3 archive synchronization metadata."""
    now = datetime.now(UTC)
    state.updated_at = now
    state.configuration.artifact_etag = etag
    state.configuration.artifact_version_id = version_id
    state.configuration.sync_digest = digest


def record_config_git_push(
    state: WorkspaceState,
    *,
    files_count: int,
    commit_hash: str | None = None,
) -> None:
    """Record metadata after a successful configuration Git push."""
    now = datetime.now(UTC)
    state.updated_at = now
    state.configuration.uploaded_at = now
    state.configuration.files_count = files_count
    if commit_hash:
        state.configuration.artifact_sha256 = commit_hash


def record_config_git_pull(
    state: WorkspaceState,
    *,
    files_count: int,
    commit_hash: str | None = None,
) -> None:
    """Record metadata after a successful configuration Git pull."""
    now = datetime.now(UTC)
    state.updated_at = now
    state.configuration.downloaded_at = now
    state.configuration.files_count = files_count
    if commit_hash:
        state.configuration.artifact_sha256 = commit_hash


def _archive_sha256(zip_path: Path) -> str:
    return hashlib.sha256(zip_path.read_bytes()).hexdigest()


def _diff_summary(diff_result: ConfigDiffResult) -> dict[str, int]:
    return {
        "added": len(diff_result.added),
        "modified": len(diff_result.modified),
        "removed": len(diff_result.removed),
    }
