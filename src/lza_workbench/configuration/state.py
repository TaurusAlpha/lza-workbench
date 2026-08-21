"""Operational state updates for configuration archive transfers."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from lza_workbench.configuration.archive import ConfigDiffResult, count_config_files
from lza_workbench.workspace.schema import WorkspaceState


def record_config_upload(
    state: WorkspaceState,
    *,
    zip_path: Path,
    manifest: dict[str, tuple[int, int]],
    diff_result: ConfigDiffResult,
    etag: str | None,
    version_id: str | None,
) -> None:
    """Record metadata after a successful configuration archive upload."""
    now = datetime.now(UTC)
    state.updated_at = now
    state.config_uploaded_at = now
    state.config_artifact_sha256 = _archive_sha256(zip_path)
    state.config_artifact_etag = etag
    state.config_artifact_version_id = version_id
    state.config_files_count = len(manifest)
    state.config_last_diff_summary = _diff_summary(diff_result)


def record_config_download(
    state: WorkspaceState,
    *,
    zip_path: Path,
    config_dir: Path,
    exclude_dirs: set[str],
    exclude_files: set[str],
    diff_result: ConfigDiffResult,
) -> None:
    """Record metadata after a successful configuration archive download."""
    now = datetime.now(UTC)
    state.updated_at = now
    state.config_downloaded_at = now
    if zip_path.exists():
        state.config_artifact_sha256 = _archive_sha256(zip_path)
    if config_dir.exists():
        state.config_files_count = count_config_files(config_dir, exclude_dirs, exclude_files)
    state.config_last_diff_summary = _diff_summary(diff_result)


def record_config_git_push(
    state: WorkspaceState,
    *,
    files_count: int,
    commit_hash: str | None = None,
) -> None:
    """Record metadata after a successful configuration Git push."""
    now = datetime.now(UTC)
    state.updated_at = now
    state.config_uploaded_at = now
    state.config_files_count = files_count
    if commit_hash:
        state.config_artifact_sha256 = commit_hash


def _archive_sha256(zip_path: Path) -> str:
    return hashlib.sha256(zip_path.read_bytes()).hexdigest()


def _diff_summary(diff_result: ConfigDiffResult) -> dict[str, int]:
    return {
        "added": len(diff_result.added),
        "modified": len(diff_result.modified),
        "removed": len(diff_result.removed),
    }

