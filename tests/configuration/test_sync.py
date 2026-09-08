"""Tests for configuration remote synchronization evaluation."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.configuration.archive import (
    compute_config_directory_digest,
)
from lza_workbench.configuration.git import GitRemoteSyncStatus
from lza_workbench.configuration.sync import (
    RemoteSyncStatus,
    evaluate_s3_remote_sync,
)
from lza_workbench.workspace.schema import (
    AwsConfig,
    CustomerConfig,
    LzaConfig,
    WorkspaceConfig,
    WorkspaceState,
)


def _make_test_workspace_state() -> WorkspaceState:
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0"),
    )
    return WorkspaceState.from_config(config)


def test_remote_sync_status_from_git() -> None:
    git_sync = GitRemoteSyncStatus(
        status="Synchronized",
        ahead=0,
        behind=0,
        summary="Up to date with origin/main",
    )
    res = RemoteSyncStatus.from_git_sync(git_sync)
    assert res.status == "Synchronized"
    assert res.is_synced is True
    assert res.summary == "Up to date with origin/main"

    none_res = RemoteSyncStatus.from_git_sync(None)
    assert none_res.status == "Not Git"
    assert none_res.is_synced is False


def test_evaluate_s3_remote_sync_offline(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "global-config.yaml").write_text("homeRegion: us-east-1\n", encoding="utf-8")

    digest = compute_config_directory_digest(config_dir, set(), set())
    state = _make_test_workspace_state()
    state.config_sync_digest = digest
    state.config_artifact_etag = "etag-123"

    res = evaluate_s3_remote_sync(
        config_dir=config_dir,
        exclude_dirs=set(),
        exclude_files=set(),
        s3_object_info=None,
        state=state,
        is_live=False,
    )
    assert res.status == "Synchronized"
    assert res.is_synced is True
    assert "Offline" in res.summary

    # Modify local file
    (config_dir / "global-config.yaml").write_text("homeRegion: eu-west-1\n", encoding="utf-8")
    res_mod = evaluate_s3_remote_sync(
        config_dir=config_dir,
        exclude_dirs=set(),
        exclude_files=set(),
        s3_object_info=None,
        state=state,
        is_live=False,
    )
    assert res_mod.status == "Ahead"
    assert res_mod.is_synced is False


def test_evaluate_s3_remote_sync_not_uploaded(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "global-config.yaml").write_text("test: 1\n", encoding="utf-8")

    res = evaluate_s3_remote_sync(
        config_dir=config_dir,
        exclude_dirs=set(),
        exclude_files=set(),
        s3_object_info={"exists": False, "error": None},
        state=None,
        is_live=True,
    )
    assert res.status == "Not Uploaded"
    assert res.is_synced is False


def test_evaluate_s3_remote_sync_metadata_match(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "global-config.yaml").write_text("test: 1\n", encoding="utf-8")

    digest = compute_config_directory_digest(config_dir, set(), set())
    s3_info = {
        "exists": True,
        "etag": "s3-etag-999",
        "metadata": {"lza-content-digest": digest},
        "error": None,
    }

    res = evaluate_s3_remote_sync(
        config_dir=config_dir,
        exclude_dirs=set(),
        exclude_files=set(),
        s3_object_info=s3_info,
        state=None,
        is_live=True,
    )
    assert res.status == "Synchronized"
    assert res.is_synced is True
    assert "s3-etag-999" in res.summary


def test_evaluate_s3_remote_sync_metadata_diverged_and_ahead(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "global-config.yaml").write_text("v2", encoding="utf-8")

    state = _make_test_workspace_state()
    state.config_sync_digest = "digest-v1"
    state.config_artifact_etag = "etag-1"

    # Local changed, remote matches state etag
    s3_info = {
        "exists": True,
        "etag": "etag-1",
        "metadata": {"lza-content-digest": "digest-v1"},
        "error": None,
    }
    res = evaluate_s3_remote_sync(
        config_dir=config_dir,
        exclude_dirs=set(),
        exclude_files=set(),
        s3_object_info=s3_info,
        state=state,
        is_live=True,
    )
    assert res.status == "Ahead"
    assert res.is_synced is False


def test_evaluate_s3_remote_sync_state_etag_fallback(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "global-config.yaml").write_text("content", encoding="utf-8")

    digest = compute_config_directory_digest(config_dir, set(), set())
    state = _make_test_workspace_state()
    state.config_sync_digest = digest
    state.config_artifact_etag = "etag-abc"

    # S3 has no user metadata
    s3_info = {
        "exists": True,
        "etag": "etag-abc",
        "metadata": {},
        "error": None,
    }
    res = evaluate_s3_remote_sync(
        config_dir=config_dir,
        exclude_dirs=set(),
        exclude_files=set(),
        s3_object_info=s3_info,
        state=state,
        is_live=True,
    )
    assert res.status == "Synchronized"
    assert res.is_synced is True



def test_evaluate_s3_remote_sync_never_synced(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "global-config.yaml").write_text("test", encoding="utf-8")

    s3_info = {
        "exists": True,
        "etag": "etag-unknown-remote",
        "metadata": {},
        "error": None,
    }
    state = _make_test_workspace_state()
    # No state.config_artifact_etag recorded
    res = evaluate_s3_remote_sync(
        config_dir=config_dir,
        exclude_dirs=set(),
        exclude_files=set(),
        s3_object_info=s3_info,
        state=state,
        is_live=True,
    )
    assert res.status == "Unknown"
    assert res.is_synced is False
    assert "Never synced" in res.summary
    assert res.details.get("never_synced") is True
