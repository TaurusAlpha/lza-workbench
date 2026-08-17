"""Tests for lza config upload command."""

from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lza_workbench.cli import main
from lza_workbench.commands.config_upload import (
    run_upload_config,
)
from lza_workbench.commands.workspace_init import run_init
from lza_workbench.core.errors import LzaError
from lza_workbench.workspace.config import load_workspace_config, write_workspace_config
from lza_workbench.workspace.paths import resolve_workspace_dir
from lza_workbench.workspace.state import load_workspace_state


@pytest.fixture
def workspace_dir(tmp_path: Path) -> Path:
    target = tmp_path / "test-customer"
    run_init(
        customer_name="Test Customer",
        workspace_dir=target,
        aws_profile="test-profile",
        aws_region="us-east-1",
        lza_version="v1.15.5",
        dry_run=False,
        force=False,
        skip_aws_check=True,
        interactive=False,
    )
    config = load_workspace_config(target)
    config.configuration.repository.type = "s3"
    write_workspace_config(target, config)
    return target


def test_resolve_workspace_dir_fails_outside_workspace(tmp_path: Path) -> None:
    with pytest.raises(LzaError, match="must be run inside an LZA workspace directory"):
        resolve_workspace_dir(tmp_path)


def test_resolve_workspace_dir_finds_workspace_from_subdir(workspace_dir: Path) -> None:
    subdir = workspace_dir / "aws-accelerator-config"
    assert resolve_workspace_dir(subdir) == workspace_dir


def test_run_upload_config_requires_bucket(workspace_dir: Path) -> None:
    with pytest.raises(LzaError, match="No S3 bucket configured"):
        run_upload_config(target_dir=workspace_dir, interactive=False)


def test_run_upload_config_requires_profile(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.bucket = "my-test-bucket"
    cfg.aws.profile = None
    write_workspace_config(workspace_dir, cfg)

    with pytest.raises(
        (LzaError, ValueError),
        match="AWS configuration requires|profile|Invalid workspace configuration",
    ):
        run_upload_config(target_dir=workspace_dir, interactive=False)


def test_run_upload_config_dry_run(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(workspace_dir, cfg)

    zip_path = run_upload_config(target_dir=workspace_dir, dry_run=True)
    assert zip_path == workspace_dir / "aws-accelerator-config.zip"


def test_run_upload_config_success(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.bucket = "my-test-bucket"
    cfg.configuration.repository.prefix = "my-prefix"
    write_workspace_config(workspace_dir, cfg)

    config_dir = workspace_dir / "aws-accelerator-config"
    (config_dir / ".DS_Store").write_text("dummy", encoding="utf-8")
    backup_dir = config_dir / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    (backup_dir / "ignored.txt").write_text("ignored", encoding="utf-8")

    mock_s3 = MagicMock()
    mock_s3.head_object.return_value = {"ETag": '"123456789"', "VersionId": "v1.0"}

    with patch("boto3.Session") as mock_session_cls:
        mock_session_cls.return_value.client.return_value = mock_s3
        zip_path = run_upload_config(target_dir=workspace_dir)

    assert zip_path == workspace_dir / "aws-accelerator-config.zip"
    assert zip_path.is_file()

    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        assert ".DS_Store" not in namelist
        assert "backup/ignored.txt" not in namelist
        assert "global-config.yaml" in namelist

    mock_s3.upload_file.assert_called_once_with(
        str(zip_path), "my-test-bucket", "my-prefix/aws-accelerator-config.zip"
    )

    state = load_workspace_state(workspace_dir)
    assert state.config_uploaded_at is not None
    assert state.config_artifact_sha256 is not None
    assert state.config_artifact_etag == "123456789"
    assert state.config_artifact_version_id == "v1.0"
    assert state.config_files_count == len(namelist)
    assert state.config_last_diff_summary == {"added": len(namelist), "modified": 0, "removed": 0}


def test_run_upload_config_diff_calculation(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(workspace_dir, cfg)

    zip_path = workspace_dir / "aws-accelerator-config.zip"

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("global-config.yaml", "old content")
        zf.writestr("deleted-file.yaml", "will be removed")

    config_dir = workspace_dir / "aws-accelerator-config"
    (config_dir / "global-config.yaml").write_text("new content", encoding="utf-8")
    (config_dir / "new-file.yaml").write_text("added file", encoding="utf-8")
    if (config_dir / "deleted-file.yaml").exists():
        (config_dir / "deleted-file.yaml").unlink()

    mock_s3 = MagicMock()
    mock_s3.head_object.return_value = {}

    with patch("boto3.Session") as mock_session_cls:
        mock_session_cls.return_value.client.return_value = mock_s3
        run_upload_config(target_dir=workspace_dir)

    state = load_workspace_state(workspace_dir)
    assert state.config_last_diff_summary is not None
    assert state.config_last_diff_summary["modified"] >= 1
    assert state.config_last_diff_summary["removed"] >= 1


def test_cli_config_upload_command(workspace_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(workspace_dir, cfg)

    monkeypatch.chdir(workspace_dir)
    exit_code = main(["config", "upload", "--dry-run"])
    assert exit_code == 0


def test_run_upload_config_custom_key_and_prefix(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.bucket = "my-test-bucket"
    cfg.configuration.repository.prefix = "custom-prefix/"
    cfg.configuration.repository.key = "custom-archive.zip"
    write_workspace_config(workspace_dir, cfg)

    mock_s3 = MagicMock()
    mock_s3.head_object.return_value = {"ETag": '"987654321"', "VersionId": "v2.0"}

    with patch("boto3.Session") as mock_session_cls:
        mock_session_cls.return_value.client.return_value = mock_s3
        zip_path = run_upload_config(target_dir=workspace_dir)

    assert zip_path == workspace_dir / "custom-archive.zip"
    mock_s3.upload_file.assert_called_once_with(
        str(zip_path), "my-test-bucket", "custom-prefix/custom-archive.zip"
    )

