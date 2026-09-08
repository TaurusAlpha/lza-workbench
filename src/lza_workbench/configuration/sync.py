"""Configuration remote synchronization status evaluation and models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lza_workbench.aws.s3 import S3ObjectObservation
from lza_workbench.configuration.archive import compute_config_directory_digest
from lza_workbench.configuration.git import GitRemoteSyncStatus
from lza_workbench.workspace.schema import WorkspaceState


@dataclass(frozen=True)
class RemoteSyncStatus:
    """Universal comparison between local configuration and remote source."""

    status: str  # Synchronized, Ahead, Behind, Diverged, No Upstream, Not Uploaded, etc.
    ahead: int = 0
    behind: int = 0
    summary: str = ""
    is_synced: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_git_sync(cls, git_sync: GitRemoteSyncStatus | None) -> RemoteSyncStatus:
        """Translate a GitRemoteSyncStatus into universal RemoteSyncStatus."""
        if git_sync is None:
            return cls(status="Not Git", summary="Not Git", is_synced=False)
        is_synced = git_sync.status == "Synchronized"
        return cls(
            status=git_sync.status,
            ahead=git_sync.ahead,
            behind=git_sync.behind,
            summary=git_sync.summary,
            is_synced=is_synced,
            details={"type": "git", "git_status": git_sync.status},
        )


def evaluate_s3_remote_sync(
    *,
    config_dir: Path,
    exclude_dirs: set[str],
    exclude_files: set[str],
    s3_object_info: S3ObjectObservation | None,
    state: WorkspaceState | None = None,
    is_live: bool = True,
) -> RemoteSyncStatus:
    """Evaluate S3 remote synchronization using metadata and recorded state (Tier 1)."""
    if not config_dir.exists():
        return RemoteSyncStatus(
            status="Missing",
            summary="Local configuration directory does not exist",
            is_synced=False,
        )

    local_digest = compute_config_directory_digest(config_dir, exclude_dirs, exclude_files)

    # Offline / No Live AWS Context
    if not is_live or s3_object_info is None:
        if state and state.config_sync_digest:
            if local_digest == state.config_sync_digest:
                etag_label = (
                    f" (ETag: {state.config_artifact_etag})"
                    if state.config_artifact_etag
                    else ""
                )
                return RemoteSyncStatus(
                    status="Synchronized",
                    summary=f"Local clean since last sync{etag_label} (Offline)",
                    is_synced=True,
                    details={"offline": True, "local_digest": local_digest},
                )

            return RemoteSyncStatus(
                status="Ahead",
                ahead=1,
                summary="Local changes since last sync (Offline)",
                is_synced=False,
                details={"offline": True, "local_digest": local_digest},
            )
        return RemoteSyncStatus(
            status="Unknown",
            summary="Sync status unavailable (Offline)",
            is_synced=False,
            details={"offline": True},
        )

    # Live S3 inspection evaluation
    if not s3_object_info.exists:
        err = s3_object_info.error
        if err:
            return RemoteSyncStatus(
                status="Unknown",
                summary=f"S3 access error: {err}",
                is_synced=False,
                details={"error": err},
            )
        return RemoteSyncStatus(
            status="Not Uploaded",
            summary="Not uploaded yet to S3",
            is_synced=False,
            details={"exists": False},
        )

    raw_etag = s3_object_info.etag
    remote_etag = raw_etag if isinstance(raw_etag, str) else None
    metadata = s3_object_info.metadata
    raw_digest = metadata.get("lza-content-digest") if isinstance(metadata, dict) else None
    remote_digest = raw_digest if isinstance(raw_digest, str) else None


    # Check if remote matches local
    if remote_digest:
        if local_digest == remote_digest:
            etag_str = f" (ETag: {remote_etag})" if remote_etag else ""
            return RemoteSyncStatus(
                status="Synchronized",
                summary=f"In Sync with S3{etag_str}",
                is_synced=True,
                details={
                    "remote_etag": remote_etag,
                    "remote_digest": remote_digest,
                    "local_digest": local_digest,
                    "matched_by": "s3_metadata",
                },
            )
    elif state and state.config_artifact_etag:
        if remote_etag == state.config_artifact_etag and state.config_sync_digest == local_digest:
            return RemoteSyncStatus(
                status="Synchronized",
                summary=f"In Sync with S3 (ETag: {remote_etag})",
                is_synced=True,
                details={
                    "remote_etag": remote_etag,
                    "local_digest": local_digest,
                    "matched_by": "state_etag",
                },
            )

    # Determine drift direction if state is recorded
    if state and state.config_sync_digest:
        local_changed = local_digest != state.config_sync_digest
        remote_changed = bool(
            (remote_digest and state.config_sync_digest != remote_digest)
            or (state.config_artifact_etag and remote_etag != state.config_artifact_etag)
        )

        if local_changed and remote_changed:
            summary = (
                "Local files and remote S3 archive both modified"
                if remote_digest
                else "Local changes and remote S3 archive both updated"
            )
            return RemoteSyncStatus(
                status="Diverged",
                ahead=1,
                behind=1,
                summary=summary,
                is_synced=False,
                details={"remote_etag": remote_etag},
            )
        if local_changed:
            return RemoteSyncStatus(
                status="Ahead",
                ahead=1,
                summary="Local changes (not pushed to S3)",
                is_synced=False,
                details={"remote_etag": remote_etag},
            )
        if remote_changed:
            return RemoteSyncStatus(
                status="Behind",
                behind=1,
                summary="Remote S3 archive updated (run 'lza config pull')",
                is_synced=False,
                details={"remote_etag": remote_etag},
            )

    if remote_digest:
        return RemoteSyncStatus(
            status="Diverged",
            ahead=1,
            behind=1,
            summary="Content digest differs from remote S3 metadata",
            is_synced=False,
            details={"remote_etag": remote_etag, "remote_digest": remote_digest},
        )

    # Path C: No S3 metadata and no recorded state (never synced via workbench)
    etag_part = f"remote ETag: {remote_etag or 'unknown'}"
    return RemoteSyncStatus(
        status="Unknown",
        summary=f"Never synced with workspace ({etag_part}, no local state)",
        is_synced=False,
        details={"remote_etag": remote_etag, "never_synced": True},
    )



__all__ = [
    "RemoteSyncStatus",
    "evaluate_s3_remote_sync",
]
