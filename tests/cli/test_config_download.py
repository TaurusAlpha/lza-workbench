"""Tests for lza config download CLI command."""

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
def s3_workspace(initialized_workspace: Path) -> Path:
    config = load_workspace_config(initialized_workspace)
    config.configuration.repository.type = "s3"
    config.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(initialized_workspace, config)
    return initialized_workspace


def test_cli_config_download_requires_bucket(
    initialized_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_workspace_config(initialized_workspace)
    config.configuration.repository.type = "s3"
    config.configuration.repository.bucket = None
    write_workspace_config(initialized_workspace, config)

    monkeypatch.chdir(initialized_workspace)
    result = cli_runner.invoke(app, ["config", "download"])
    assert result.exit_code == 1
    assert "No S3 bucket configured" in (result.output or str(result.exception))


def test_cli_config_download_dry_run(
    s3_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(s3_workspace)
    result = cli_runner.invoke(app, ["config", "download", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry run" in result.output


def test_cli_config_download_force_required_when_non_empty(
    s3_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_dir = s3_workspace / "aws-accelerator-config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "existing.yaml").write_text("content", encoding="utf-8")

    monkeypatch.chdir(s3_workspace)
    with patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val:
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = cli_runner.invoke(app, ["config", "download"])

    assert result.exit_code == 1
    assert "not empty" in (result.output or str(result.exception))


def test_cli_config_download_success(
    s3_workspace: Path,
    cli_runner: CliRunner,
    sample_config_zip: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_dir = s3_workspace / "aws-accelerator-config"
    config_dir.mkdir(parents=True, exist_ok=True)
    for item in config_dir.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    git_dir = config_dir / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    (config_dir / "global-config.yaml").write_text("old content", encoding="utf-8")
    (config_dir / "old-file.yaml").write_text("old file", encoding="utf-8")

    def fake_download(bucket: str, key: str, filename: str) -> None:
        sample_config_zip(
            Path(filename),
            {
                "aws-accelerator-config/global-config.yaml": "new content",
                "aws-accelerator-config/organization-config.yaml": "org content",
                "aws-accelerator-config/accounts-config.yaml": "accounts content",
                "aws-accelerator-config/network-config.yaml": "network content",
                "aws-accelerator-config/security-config.yaml": "security content",
                "aws-accelerator-config/iam-config.yaml": "iam content",
                "aws-accelerator-config/new-file.yaml": "added file",
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
        result = cli_runner.invoke(app, ["config", "download", "--force"])

    assert result.exit_code == 0
    assert (config_dir / "global-config.yaml").read_text(encoding="utf-8") == "new content"
    assert (config_dir / "new-file.yaml").read_text(encoding="utf-8") == "added file"
    assert not (config_dir / "old-file.yaml").exists()
    assert (git_dir / "HEAD").is_file()
    assert (s3_workspace / "aws-accelerator-config.zip").is_file()

    state = load_workspace_state(s3_workspace)
    assert state.config_downloaded_at is not None
    assert state.config_artifact_sha256 is not None
    assert state.config_files_count == 7
    assert state.config_last_diff_summary == {"added": 6, "modified": 1, "removed": 1}


def test_cli_config_download_without_extract(
    s3_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_download(bucket: str, key: str, filename: str) -> None:
        Path(filename).write_bytes(b"zip binary bytes")

    mock_s3 = MagicMock()
    mock_s3.download_file.side_effect = fake_download

    monkeypatch.chdir(s3_workspace)
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client", return_value=mock_s3),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = cli_runner.invoke(app, ["config", "download", "--force", "--no-extract"])

    assert result.exit_code == 0
    assert (s3_workspace / "aws-accelerator-config.zip").is_file()

    state = load_workspace_state(s3_workspace)
    assert state.config_downloaded_at is not None


def test_cli_config_download_interactive_declined(
    s3_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_dir = s3_workspace / "aws-accelerator-config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "existing.yaml").write_text("content", encoding="utf-8")

    monkeypatch.chdir(s3_workspace)
    with patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val:
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = cli_runner.invoke(app, ["config", "download"], input="n\n")

    assert result.exit_code != 0


def test_cli_config_download_custom_key_and_prefix(
    s3_workspace: Path,
    cli_runner: CliRunner,
    sample_config_zip: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = load_workspace_config(s3_workspace)
    cfg.configuration.repository.prefix = "custom-prefix/"
    cfg.configuration.repository.key = "custom-archive.zip"
    write_workspace_config(s3_workspace, cfg)

    mock_s3 = MagicMock()

    def fake_download(bucket: str, key: str, filename: str) -> None:
        sample_config_zip(Path(filename))

    mock_s3.download_file.side_effect = fake_download

    monkeypatch.chdir(s3_workspace)
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client", return_value=mock_s3),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = cli_runner.invoke(app, ["config", "download", "--force"])

    assert result.exit_code == 0
    mock_s3.download_file.assert_called_once_with(
        "my-test-bucket",
        "custom-prefix/custom-archive.zip",
        str(s3_workspace / "custom-archive.zip"),
    )
