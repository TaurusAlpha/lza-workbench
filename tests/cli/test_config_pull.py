"""Tests for lza config pull and unified remote-to-local synchronization CLI command."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from lza_workbench.cli import app
from lza_workbench.workspace.config import load_workspace_config, write_workspace_config
from lza_workbench.workspace.state import load_workspace_state


@pytest.fixture
def s3_workspace(configured_workspace: Path) -> Path:
    config = load_workspace_config(configured_workspace)
    config.configuration.repository.type = "s3"
    config.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(configured_workspace, config)
    return configured_workspace


def test_pull_s3_dry_run(
    s3_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(s3_workspace)
    result = cli_runner.invoke(app, ["config", "pull", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert "s3" in result.output


def test_pull_s3_success(
    s3_workspace: Path,
    cli_runner: CliRunner,
    sample_config_zip: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_dir = s3_workspace / "aws-accelerator-config"
    for item in config_dir.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    def fake_download(bucket: str, key: str, filename: str) -> None:
        sample_config_zip(
            Path(filename),
            {
                "aws-accelerator-config/global-config.yaml": "new global content",
                "aws-accelerator-config/organization-config.yaml": "new org content",
                "aws-accelerator-config/accounts-config.yaml": "new accounts content",
                "aws-accelerator-config/network-config.yaml": "new network content",
                "aws-accelerator-config/security-config.yaml": "new security content",
                "aws-accelerator-config/iam-config.yaml": "new iam content",
            },
        )

    mock_s3 = MagicMock()
    mock_s3.download_file.side_effect = fake_download

    monkeypatch.chdir(s3_workspace)
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client", return_value=mock_s3),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = cli_runner.invoke(app, ["config", "pull", "--force"])

    assert result.exit_code == 0
    assert (config_dir / "global-config.yaml").read_text(encoding="utf-8") == "new global content"

    state = load_workspace_state(s3_workspace)
    assert state.config_downloaded_at is not None
    assert state.config_files_count == 6


def test_download_alias_s3(
    s3_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(s3_workspace)
    result = cli_runner.invoke(app, ["config", "download", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry run" in result.output


def test_pull_codecommit_dry_run(
    configured_workspace: Path,
    cli_runner: CliRunner,
    init_git_repo: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = load_workspace_config(configured_workspace)
    cfg.configuration.repository.type = "codecommit"
    cfg.configuration.repository.repository_name = "my-config-repo"
    write_workspace_config(configured_workspace, cfg)

    config_dir = configured_workspace / "aws-accelerator-config"
    init_git_repo(config_dir, commit=True)

    monkeypatch.chdir(configured_workspace)
    result = cli_runner.invoke(app, ["config", "pull", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert "codecommit" in result.output


def test_pull_codecommit_success(
    configured_workspace: Path,
    cli_runner: CliRunner,
    init_git_repo: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = load_workspace_config(configured_workspace)
    cfg.configuration.repository.type = "codecommit"
    cfg.configuration.repository.repository_name = "my-config-repo"
    write_workspace_config(configured_workspace, cfg)

    config_dir = configured_workspace / "aws-accelerator-config"
    init_git_repo(config_dir, commit=True)

    monkeypatch.chdir(configured_workspace)
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.workflows.config_pull.fetch_git_remote") as mock_fetch,
        patch("lza_workbench.workflows.config_pull.pull_git_branch") as mock_pull,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = cli_runner.invoke(app, ["config", "pull"])

    assert result.exit_code == 0
    mock_fetch.assert_called_once_with(config_dir, remote="origin")
    mock_pull.assert_called_once_with(config_dir, remote="origin", branch="main")

    git_config_content = (config_dir / ".git" / "config").read_text(encoding="utf-8")
    assert "codecommit credential-helper $@" in git_config_content
    assert "UseHttpPath = true" in git_config_content

    state = load_workspace_state(configured_workspace)
    assert state.config_downloaded_at is not None


def test_pull_git_fails_on_uncommitted_without_force(
    configured_workspace: Path,
    cli_runner: CliRunner,
    init_git_repo: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = load_workspace_config(configured_workspace)
    cfg.configuration.repository.type = "git"
    cfg.configuration.repository.repository = "https://github.com/my-org/my-repo.git"
    write_workspace_config(configured_workspace, cfg)

    config_dir = configured_workspace / "aws-accelerator-config"
    init_git_repo(config_dir, commit=True)
    (config_dir / "uncommitted.txt").write_text("modified", encoding="utf-8")

    monkeypatch.chdir(configured_workspace)
    with patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val:
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = cli_runner.invoke(app, ["config", "pull"])

    assert result.exit_code == 1
    assert "contains uncommitted changes" in (result.output or str(result.exception))


def test_pull_git_stashes_uncommitted_with_force(
    configured_workspace: Path,
    cli_runner: CliRunner,
    init_git_repo: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = load_workspace_config(configured_workspace)
    cfg.configuration.repository.type = "git"
    cfg.configuration.repository.repository = "https://github.com/my-org/my-repo.git"
    write_workspace_config(configured_workspace, cfg)

    config_dir = configured_workspace / "aws-accelerator-config"
    init_git_repo(config_dir, commit=True)
    (config_dir / "uncommitted.txt").write_text("modified", encoding="utf-8")

    monkeypatch.chdir(configured_workspace)
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.workflows.config_pull.fetch_git_remote"),
        patch("lza_workbench.workflows.config_pull.pull_git_branch"),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = cli_runner.invoke(app, ["config", "pull", "--force"])

    assert result.exit_code == 0
    assert not (config_dir / "uncommitted.txt").exists()


def test_pull_git_interactive_stash_confirmed(
    configured_workspace: Path,
    cli_runner: CliRunner,
    init_git_repo: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = load_workspace_config(configured_workspace)
    cfg.configuration.repository.type = "git"
    cfg.configuration.repository.repository = "https://github.com/my-org/my-repo.git"
    write_workspace_config(configured_workspace, cfg)

    config_dir = configured_workspace / "aws-accelerator-config"
    init_git_repo(config_dir, commit=True)
    (config_dir / "uncommitted.txt").write_text("modified", encoding="utf-8")

    monkeypatch.chdir(configured_workspace)
    with (
        patch("lza_workbench.cli.main._is_interactive", return_value=True),
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.workflows.config_pull.fetch_git_remote"),
        patch("lza_workbench.workflows.config_pull.pull_git_branch"),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = cli_runner.invoke(app, ["config", "pull"], input="y\n")

    assert result.exit_code == 0
    assert not (config_dir / "uncommitted.txt").exists()


def test_pull_git_interactive_stash_declined(
    configured_workspace: Path,
    cli_runner: CliRunner,
    init_git_repo: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = load_workspace_config(configured_workspace)
    cfg.configuration.repository.type = "git"
    cfg.configuration.repository.repository = "https://github.com/my-org/my-repo.git"
    write_workspace_config(configured_workspace, cfg)

    config_dir = configured_workspace / "aws-accelerator-config"
    init_git_repo(config_dir, commit=True)
    (config_dir / "uncommitted.txt").write_text("modified", encoding="utf-8")

    monkeypatch.chdir(configured_workspace)
    with (
        patch("lza_workbench.cli.main._is_interactive", return_value=True),
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = cli_runner.invoke(app, ["config", "pull"], input="n\n")

    assert result.exit_code != 0


