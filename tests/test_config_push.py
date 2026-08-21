"""Tests for lza config push and unified local-to-remote synchronization workflow."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lza_workbench.cli.commands.config_push import config_push_command as run_push_config
from lza_workbench.cli.commands.config_upload import config_upload_command as run_upload_config
from lza_workbench.cli.main import main
from lza_workbench.errors import LzaError
from lza_workbench.workflows.config_init import init_config_workflow
from lza_workbench.workflows.workspace_init import init_workspace_workflow
from lza_workbench.workspace.config import load_workspace_config, write_workspace_config
from lza_workbench.workspace.state import load_workspace_state


@pytest.fixture
def workspace_dir(tmp_path: Path) -> Path:
    target = tmp_path / "test-customer"
    init_workspace_workflow(
        customer_name="Test Customer",
        workspace_dir=target,
        aws_profile="test-profile",
        aws_region="us-east-1",
        lza_version="v1.15.5",
        dry_run=False,
        force=False,
        skip_aws_check=True,
    )
    init_config_workflow(target_dir=target)
    return target


def _init_local_git_repo(config_dir: Path, commit: bool = True) -> None:
    """Initialize a local git repository in config_dir with initial commit."""
    subprocess.run(["git", "init", "-b", "main"], cwd=config_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "LZA Tester"],
        cwd=config_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "tester@example.com"],
        cwd=config_dir,
        check=True,
        capture_output=True,
    )
    if commit:
        subprocess.run(["git", "add", "."], cwd=config_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial LZA configuration"],
            cwd=config_dir,
            check=True,
            capture_output=True,
        )


def test_push_s3_dry_run(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.type = "s3"
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(workspace_dir, cfg)

    result = run_push_config(target_dir=workspace_dir, dry_run=True)
    assert result.dry_run is True
    assert result.repository_type == "s3"
    assert result.s3_bucket == "my-test-bucket"
    assert result.zip_path == workspace_dir / "aws-accelerator-config.zip"


def test_push_s3_success(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.type = "s3"
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(workspace_dir, cfg)

    mock_s3 = MagicMock()
    mock_s3.head_object.return_value = {"ETag": '"12345"', "VersionId": "v1"}

    with patch("boto3.Session") as mock_session_cls:
        mock_session_cls.return_value.client.return_value = mock_s3
        result = run_push_config(target_dir=workspace_dir, dry_run=False)

    assert result.dry_run is False
    assert result.repository_type == "s3"
    assert result.zip_path == workspace_dir / "aws-accelerator-config.zip"
    assert result.zip_path.is_file()

    state = load_workspace_state(workspace_dir)
    assert state.config_uploaded_at is not None
    assert state.config_artifact_etag == "12345"


def test_upload_alias_s3(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.type = "s3"
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(workspace_dir, cfg)

    zip_path = run_upload_config(target_dir=workspace_dir, dry_run=True)
    assert zip_path == workspace_dir / "aws-accelerator-config.zip"


def test_push_codecommit_fails_if_not_git_repo(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.type = "codecommit"
    cfg.configuration.repository.repository_name = "my-config-repo"
    write_workspace_config(workspace_dir, cfg)

    with pytest.raises(LzaError, match="is not a Git repository"):
        run_push_config(target_dir=workspace_dir)


def test_push_codecommit_fails_if_no_commits(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.type = "codecommit"
    cfg.configuration.repository.repository_name = "my-config-repo"
    write_workspace_config(workspace_dir, cfg)

    config_dir = workspace_dir / "aws-accelerator-config"
    _init_local_git_repo(config_dir, commit=False)

    with pytest.raises(LzaError, match="has no commits"):
        run_push_config(target_dir=workspace_dir)


def test_push_codecommit_fails_if_uncommitted_changes(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.type = "codecommit"
    cfg.configuration.repository.repository_name = "my-config-repo"
    write_workspace_config(workspace_dir, cfg)

    config_dir = workspace_dir / "aws-accelerator-config"
    _init_local_git_repo(config_dir, commit=True)

    (config_dir / "new_file.txt").write_text("uncommitted", encoding="utf-8")

    with pytest.raises(LzaError, match="contains uncommitted changes"):
        run_push_config(target_dir=workspace_dir)


def test_push_codecommit_dry_run(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.type = "codecommit"
    cfg.configuration.repository.repository_name = "my-config-repo"
    write_workspace_config(workspace_dir, cfg)

    config_dir = workspace_dir / "aws-accelerator-config"
    _init_local_git_repo(config_dir, commit=True)

    result = run_push_config(target_dir=workspace_dir, dry_run=True)
    assert result.dry_run is True
    assert result.repository_type == "codecommit"
    assert result.git_remote == "origin"
    assert (
        result.git_remote_url
        == "https://git-codecommit.us-east-1.amazonaws.com/v1/repos/my-config-repo"
    )
    assert result.git_branch == "main"
    assert result.git_commit != ""
    assert result.files_count is not None and result.files_count > 0


def test_push_codecommit_success(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.type = "codecommit"
    cfg.configuration.repository.repository_name = "my-config-repo"
    write_workspace_config(workspace_dir, cfg)

    config_dir = workspace_dir / "aws-accelerator-config"
    _init_local_git_repo(config_dir, commit=True)

    with patch("lza_workbench.workflows.config_push.push_git_branch") as mock_push:
        result = run_push_config(target_dir=workspace_dir, dry_run=False)

    assert result.dry_run is False
    assert result.repository_type == "codecommit"
    mock_push.assert_called_once_with(config_dir, remote="origin", branch="main", dry_run=False)

    state = load_workspace_state(workspace_dir)
    assert state.config_uploaded_at is not None
    assert state.config_files_count == result.files_count
    assert state.config_artifact_sha256 == result.git_commit


def test_push_codeconnection_dry_run_and_success(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.type = "codeconnection"
    cfg.configuration.repository.owner = "my-org"
    cfg.configuration.repository.repository_name = "my-repo"
    cfg.configuration.repository.codeconnection_arn = (
        "arn:aws:codeconnections:us-east-1:123456789012:connection/abcdef"
    )
    cfg.configuration.repository.repository = "https://github.com/my-org/my-repo.git"
    write_workspace_config(workspace_dir, cfg)

    config_dir = workspace_dir / "aws-accelerator-config"
    _init_local_git_repo(config_dir, commit=True)

    result_dry = run_push_config(target_dir=workspace_dir, dry_run=True)
    assert result_dry.dry_run is True
    assert result_dry.repository_type == "codeconnection"
    assert result_dry.git_remote_url == "https://github.com/my-org/my-repo.git"

    with patch("lza_workbench.workflows.config_push.push_git_branch") as mock_push:
        result = run_push_config(target_dir=workspace_dir, dry_run=False)

    assert result.dry_run is False
    mock_push.assert_called_once_with(config_dir, remote="origin", branch="main", dry_run=False)


def test_cli_push_command(workspace_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.type = "s3"
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(workspace_dir, cfg)

    monkeypatch.chdir(workspace_dir)
    exit_code = main(["config", "push", "--dry-run"])
    assert exit_code == 0
