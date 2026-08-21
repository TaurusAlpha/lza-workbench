"""Tests for lza config pull and unified remote-to-local synchronization workflow."""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lza_workbench.cli.commands.config_download import (
    config_download_command as run_download_config,
)
from lza_workbench.cli.commands.config_pull import config_pull_command as run_pull_config
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


def test_pull_s3_dry_run(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.type = "s3"
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(workspace_dir, cfg)

    result = run_pull_config(target_dir=workspace_dir, dry_run=True)
    assert result.dry_run is True
    assert result.repository_type == "s3"
    assert result.s3_bucket == "my-test-bucket"
    assert result.zip_path == workspace_dir / "aws-accelerator-config.zip"


def test_pull_s3_success(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.type = "s3"
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(workspace_dir, cfg)

    config_dir = workspace_dir / "aws-accelerator-config"
    for item in config_dir.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    def fake_download(bucket: str, key: str, filename: str) -> None:
        p = Path(filename)
        p.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(str(p), "w") as zf:
            zf.writestr("aws-accelerator-config/global-config.yaml", "new global content")
            zf.writestr("aws-accelerator-config/organization-config.yaml", "new org content")
            zf.writestr("aws-accelerator-config/accounts-config.yaml", "new accounts content")
            zf.writestr("aws-accelerator-config/network-config.yaml", "new network content")
            zf.writestr("aws-accelerator-config/security-config.yaml", "new security content")

    mock_s3 = MagicMock()
    mock_s3.download_file.side_effect = fake_download

    with patch("boto3.Session") as mock_session_cls:
        mock_session_cls.return_value.client.return_value = mock_s3
        result = run_pull_config(target_dir=workspace_dir, force=True)

    assert result.dry_run is False
    assert result.repository_type == "s3"
    assert (config_dir / "global-config.yaml").read_text(encoding="utf-8") == "new global content"

    state = load_workspace_state(workspace_dir)
    assert state.config_downloaded_at is not None
    assert state.config_files_count == 5


def test_download_alias_s3(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.type = "s3"
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(workspace_dir, cfg)

    path = run_download_config(target_dir=workspace_dir, dry_run=True)
    assert path == workspace_dir / "aws-accelerator-config"


def test_pull_codecommit_dry_run(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.type = "codecommit"
    cfg.configuration.repository.repository_name = "my-config-repo"
    write_workspace_config(workspace_dir, cfg)

    config_dir = workspace_dir / "aws-accelerator-config"
    _init_local_git_repo(config_dir, commit=True)

    result = run_pull_config(target_dir=workspace_dir, dry_run=True)
    assert result.dry_run is True
    assert result.repository_type == "codecommit"
    assert result.git_remote == "origin"
    assert (
        result.git_remote_url
        == "https://git-codecommit.us-east-1.amazonaws.com/v1/repos/my-config-repo"
    )
    assert result.git_branch == "main"
    assert result.git_commit != ""


def test_pull_codecommit_success(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.type = "codecommit"
    cfg.configuration.repository.repository_name = "my-config-repo"
    write_workspace_config(workspace_dir, cfg)

    config_dir = workspace_dir / "aws-accelerator-config"
    _init_local_git_repo(config_dir, commit=True)

    with patch("lza_workbench.workflows.config_pull.fetch_git_remote") as mock_fetch, \
         patch("lza_workbench.workflows.config_pull.pull_git_branch") as mock_pull:
        result = run_pull_config(target_dir=workspace_dir, dry_run=False)

    assert result.dry_run is False
    assert result.repository_type == "codecommit"
    mock_fetch.assert_called_once_with(config_dir, remote="origin")
    mock_pull.assert_called_once_with(config_dir, remote="origin", branch="main")

    state = load_workspace_state(workspace_dir)
    assert state.config_downloaded_at is not None
    assert state.config_files_count == result.files_count
    assert state.config_artifact_sha256 == result.git_commit


def test_pull_git_fails_on_uncommitted_without_force(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.type = "git"
    cfg.configuration.repository.repository = "https://github.com/my-org/my-repo.git"
    write_workspace_config(workspace_dir, cfg)

    config_dir = workspace_dir / "aws-accelerator-config"
    _init_local_git_repo(config_dir, commit=True)
    (config_dir / "uncommitted.txt").write_text("modified", encoding="utf-8")

    with pytest.raises(LzaError, match="contains uncommitted changes"):
        run_pull_config(target_dir=workspace_dir, force=False)


def test_pull_git_stashes_uncommitted_with_force(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.type = "git"
    cfg.configuration.repository.repository = "https://github.com/my-org/my-repo.git"
    write_workspace_config(workspace_dir, cfg)

    config_dir = workspace_dir / "aws-accelerator-config"
    _init_local_git_repo(config_dir, commit=True)
    (config_dir / "uncommitted.txt").write_text("modified", encoding="utf-8")

    with patch("lza_workbench.workflows.config_pull.fetch_git_remote"), \
         patch("lza_workbench.workflows.config_pull.pull_git_branch"):
        result = run_pull_config(target_dir=workspace_dir, force=True)

    assert result.dry_run is False
    assert result.stashed_changes is True
    assert not (config_dir / "uncommitted.txt").exists()


def test_cli_config_pull_command(workspace_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.type = "s3"
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(workspace_dir, cfg)

    monkeypatch.chdir(workspace_dir)
    exit_code = main(["config", "pull", "--dry-run"])
    assert exit_code == 0
