"""Tests for lza config push and unified local-to-remote synchronization CLI command."""

from __future__ import annotations

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


def test_push_s3_dry_run(
    s3_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(s3_workspace)
    result = cli_runner.invoke(app, ["config", "push", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert "s3" in result.output


def test_push_s3_success(
    s3_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_s3 = MagicMock()
    mock_s3.head_object.return_value = {"ETag": '"12345"', "VersionId": "v1"}

    monkeypatch.chdir(s3_workspace)
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client", return_value=mock_s3),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = cli_runner.invoke(app, ["config", "push"])

    assert result.exit_code == 0
    assert (s3_workspace / "aws-accelerator-config.zip").is_file()

    state = load_workspace_state(s3_workspace)
    assert state.config_uploaded_at is not None
    assert state.config_artifact_etag == "12345"


def test_upload_alias_s3(
    s3_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(s3_workspace)
    result = cli_runner.invoke(app, ["config", "upload", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry run" in result.output


def test_push_codecommit_fails_if_not_git_repo(
    configured_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = load_workspace_config(configured_workspace)
    cfg.configuration.repository.type = "codecommit"
    cfg.configuration.repository.repository_name = "my-config-repo"
    write_workspace_config(configured_workspace, cfg)

    monkeypatch.chdir(configured_workspace)
    with patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val:
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = cli_runner.invoke(app, ["config", "push"])

    assert result.exit_code == 1
    assert "is not a Git repository" in (result.output or str(result.exception))


def test_push_codecommit_fails_if_no_commits(
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
    init_git_repo(config_dir, commit=False)

    monkeypatch.chdir(configured_workspace)
    with patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val:
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = cli_runner.invoke(app, ["config", "push"])

    assert result.exit_code == 1
    assert "has no commits" in (result.output or str(result.exception))


def test_push_codecommit_fails_if_uncommitted_changes(
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
    (config_dir / "new_file.txt").write_text("uncommitted", encoding="utf-8")

    monkeypatch.chdir(configured_workspace)
    with patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val:
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = cli_runner.invoke(app, ["config", "push"])

    assert result.exit_code == 1
    assert "contains uncommitted changes" in (result.output or str(result.exception))


def test_push_codecommit_dry_run(
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
    result = cli_runner.invoke(app, ["config", "push", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert "codecommit" in result.output


def test_push_codecommit_success(
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
        patch("lza_workbench.workflows.config_push.push_git_branch") as mock_push,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = cli_runner.invoke(app, ["config", "push"])

    assert result.exit_code == 0
    mock_push.assert_called_once_with(config_dir, remote="origin", branch="main", dry_run=False)

    git_config_content = (config_dir / ".git" / "config").read_text(encoding="utf-8")
    assert "codecommit credential-helper $@" in git_config_content
    assert "UseHttpPath = true" in git_config_content

    state = load_workspace_state(configured_workspace)
    assert state.config_uploaded_at is not None


def test_push_codeconnection_dry_run_and_success(
    configured_workspace: Path,
    cli_runner: CliRunner,
    init_git_repo: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = load_workspace_config(configured_workspace)
    cfg.configuration.repository.type = "codeconnection"
    cfg.configuration.repository.owner = "my-org"
    cfg.configuration.repository.repository_name = "my-repo"
    cfg.configuration.repository.codeconnection_arn = (
        "arn:aws:codeconnections:us-east-1:123456789012:connection/abcdef"
    )
    cfg.configuration.repository.repository = "https://github.com/my-org/my-repo.git"
    write_workspace_config(configured_workspace, cfg)

    config_dir = configured_workspace / "aws-accelerator-config"
    init_git_repo(config_dir, commit=True)

    monkeypatch.chdir(configured_workspace)
    result_dry = cli_runner.invoke(app, ["config", "push", "--dry-run"])
    assert result_dry.exit_code == 0
    assert "Dry run" in result_dry.output
    assert "codeconnection" in result_dry.output

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.workflows.config_push.push_git_branch") as mock_push,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = cli_runner.invoke(app, ["config", "push"])

    assert result.exit_code == 0
    mock_push.assert_called_once_with(config_dir, remote="origin", branch="main", dry_run=False)
