"""Tests for lza config upload CLI command."""

from __future__ import annotations

import zipfile
from pathlib import Path
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
    config.aws.account_id = "123456789012"
    config.configuration.repository.bucket = "aws-accelerator-config-123456789012-eu-west-1"
    write_workspace_config(configured_workspace, config)
    return configured_workspace


def test_cli_config_upload_requires_account_id_for_s3_destination(
    configured_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_workspace_config(configured_workspace)
    config.configuration.repository.bucket = None
    config.aws.account_id = None
    write_workspace_config(configured_workspace, config)

    monkeypatch.chdir(configured_workspace)
    result = cli_runner.invoke(app, ["config", "upload"])
    assert result.exit_code == 1
    assert "Cannot resolve the LZA configuration S3 bucket" in (
        result.output or str(result.exception)
    )


def test_cli_config_upload_dry_run(
    s3_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(s3_workspace)
    result = cli_runner.invoke(app, ["config", "upload", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry run" in result.output


def test_cli_config_upload_success(
    s3_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_dir = s3_workspace / "aws-accelerator-config"
    (config_dir / ".DS_Store").write_text("dummy", encoding="utf-8")
    backup_dir = config_dir / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    (backup_dir / "ignored.txt").write_text("ignored", encoding="utf-8")

    mock_s3 = MagicMock()
    mock_s3.head_object.return_value = {"ETag": '"123456789"', "VersionId": "v1.0"}

    monkeypatch.chdir(s3_workspace)
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client", return_value=mock_s3),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = cli_runner.invoke(app, ["config", "upload"])

    assert result.exit_code == 0
    zip_path = s3_workspace / "aws-accelerator-config.zip"
    assert zip_path.is_file()

    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        assert ".DS_Store" not in namelist
        assert "backup/ignored.txt" not in namelist
        assert "global-config.yaml" in namelist

    mock_s3.upload_file.assert_called_once_with(
        str(zip_path),
        "aws-accelerator-config-123456789012-eu-west-1",
        "zipped/aws-accelerator-config.zip",
    )

    state = load_workspace_state(s3_workspace)
    assert state.config_uploaded_at is not None
    assert state.config_artifact_sha256 is not None
    assert state.config_artifact_etag == "123456789"
    assert state.config_artifact_version_id == "v1.0"
    assert state.config_files_count == len(namelist)
    assert state.config_last_diff_summary == {"added": len(namelist), "modified": 0, "removed": 0}
