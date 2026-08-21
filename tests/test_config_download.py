"""Tests for lza config download command."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer

from lza_workbench.cli.commands.config_download import (
    config_download_command as run_download_config,
)
from lza_workbench.cli.main import main
from lza_workbench.errors import LzaError
from lza_workbench.workflows.workspace_init import init_workspace_workflow
from lza_workbench.workspace.config import load_workspace_config, write_workspace_config
from lza_workbench.workspace.paths import resolve_workspace_dir
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
    config = load_workspace_config(target)
    config.configuration.repository.type = "s3"
    write_workspace_config(target, config)
    return target


def test_resolve_workspace_dir_fails_outside_workspace(tmp_path: Path) -> None:
    with pytest.raises(LzaError, match="must be run inside an LZA workspace directory"):
        resolve_workspace_dir(tmp_path)


def test_resolve_workspace_dir_finds_workspace_from_subdir(workspace_dir: Path) -> None:
    subdir = workspace_dir / "aws-accelerator-config"
    subdir.mkdir(parents=True, exist_ok=True)
    assert resolve_workspace_dir(subdir) == workspace_dir


def test_run_download_config_requires_bucket(workspace_dir: Path) -> None:
    with pytest.raises(LzaError, match="No S3 bucket configured"):
        run_download_config(target_dir=workspace_dir, interactive=False)


def test_run_download_config_dry_run(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(workspace_dir, cfg)

    path = run_download_config(target_dir=workspace_dir, dry_run=True)
    assert path == workspace_dir / "aws-accelerator-config"


def test_run_download_config_force_required(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(workspace_dir, cfg)

    config_dir = workspace_dir / "aws-accelerator-config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "existing.yaml").write_text("content", encoding="utf-8")

    with pytest.raises(LzaError, match="not empty"):
        run_download_config(target_dir=workspace_dir, force=False, interactive=False)


def test_run_download_config_success(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(workspace_dir, cfg)

    config_dir = workspace_dir / "aws-accelerator-config"
    config_dir.mkdir(parents=True, exist_ok=True)
    for item in config_dir.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    git_dir = config_dir / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    # Write initial file to test modification diff
    (config_dir / "global-config.yaml").write_text("old content", encoding="utf-8")
    (config_dir / "old-file.yaml").write_text("old file", encoding="utf-8")

    def fake_download(bucket: str, key: str, filename: str) -> None:
        p = Path(filename)
        p.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(str(p), "w") as zf:
            zf.writestr("aws-accelerator-config/global-config.yaml", "new content")
            zf.writestr("aws-accelerator-config/new-file.yaml", "added file")

    mock_s3 = MagicMock()
    mock_s3.download_file.side_effect = fake_download

    with patch("boto3.Session") as mock_session_cls:
        mock_session_cls.return_value.client.return_value = mock_s3
        path = run_download_config(target_dir=workspace_dir, force=True)

    assert path == workspace_dir / "aws-accelerator-config"
    assert (path / "global-config.yaml").read_text(encoding="utf-8") == "new content"
    assert (path / "new-file.yaml").read_text(encoding="utf-8") == "added file"
    assert not (path / "old-file.yaml").exists()
    assert (git_dir / "HEAD").is_file()
    assert (workspace_dir / "aws-accelerator-config.zip").is_file()

    state = load_workspace_state(workspace_dir)
    assert state.config_downloaded_at is not None
    assert state.config_artifact_sha256 is not None
    assert state.config_files_count == 2
    assert state.config_last_diff_summary == {"added": 1, "modified": 1, "removed": 1}


def test_run_download_config_without_extract(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(workspace_dir, cfg)

    def fake_download(bucket: str, key: str, filename: str) -> None:
        p = Path(filename)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"zip binary bytes")

    mock_s3 = MagicMock()
    mock_s3.download_file.side_effect = fake_download

    with patch("boto3.Session") as mock_session_cls:
        mock_session_cls.return_value.client.return_value = mock_s3
        run_download_config(target_dir=workspace_dir, force=True, extract=False)

    assert (workspace_dir / "aws-accelerator-config.zip").is_file()
    assert not (workspace_dir / "aws-accelerator-config").exists()

    state = load_workspace_state(workspace_dir)
    assert state.config_downloaded_at is not None


def test_cli_config_download_command(
    workspace_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(workspace_dir, cfg)

    monkeypatch.chdir(workspace_dir)
    exit_code = main(["config", "download", "--dry-run"])
    assert exit_code == 0


def test_run_download_config_interactive_declined(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(workspace_dir, cfg)

    config_dir = workspace_dir / "aws-accelerator-config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "existing.yaml").write_text("content", encoding="utf-8")

    with patch("typer.confirm", return_value=False):
        with pytest.raises(typer.Abort):
            run_download_config(target_dir=workspace_dir, force=False, interactive=True)


def test_run_download_config_interactive_confirmed(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(workspace_dir, cfg)

    config_dir = workspace_dir / "aws-accelerator-config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "existing.yaml").write_text("content", encoding="utf-8")

    def fake_download(bucket: str, key: str, filename: str) -> None:
        p = Path(filename)
        p.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(str(p), "w") as zf:
            zf.writestr("aws-accelerator-config/global-config.yaml", "confirmed content")

    mock_s3 = MagicMock()
    mock_s3.download_file.side_effect = fake_download

    with patch("boto3.Session") as mock_session_cls:
        mock_session_cls.return_value.client.return_value = mock_s3
        with patch("typer.confirm", return_value=True):
            path = run_download_config(target_dir=workspace_dir, force=False, interactive=True)

    assert (path / "global-config.yaml").read_text(encoding="utf-8") == "confirmed content"


def test_cli_config_download_command_fails_on_non_empty_without_force(
    workspace_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(workspace_dir, cfg)

    config_dir = workspace_dir / "aws-accelerator-config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "existing.yaml").write_text("content", encoding="utf-8")

    monkeypatch.chdir(workspace_dir)
    exit_code = main(["config", "download"])
    assert exit_code == 1


def test_cli_config_download_command_succeeds_with_force(
    workspace_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(workspace_dir, cfg)

    config_dir = workspace_dir / "aws-accelerator-config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "existing.yaml").write_text("content", encoding="utf-8")

    def fake_download(bucket: str, key: str, filename: str) -> None:
        p = Path(filename)
        p.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(str(p), "w") as zf:
            zf.writestr("aws-accelerator-config/global-config.yaml", "force content")

    mock_s3 = MagicMock()
    mock_s3.download_file.side_effect = fake_download

    monkeypatch.chdir(workspace_dir)
    with patch("boto3.Session") as mock_session_cls:
        mock_session_cls.return_value.client.return_value = mock_s3
        exit_code = main(["config", "download", "--force"])

    assert exit_code == 0
    assert (config_dir / "global-config.yaml").read_text(encoding="utf-8") == "force content"


def test_run_download_config_custom_key_and_prefix(workspace_dir: Path) -> None:
    cfg = load_workspace_config(workspace_dir)
    cfg.configuration.repository.bucket = "my-test-bucket"
    cfg.configuration.repository.prefix = "custom-prefix/"
    cfg.configuration.repository.key = "custom-archive.zip"
    write_workspace_config(workspace_dir, cfg)

    mock_s3 = MagicMock()

    def fake_download(bucket: str, key: str, filename: str) -> None:
        p = Path(filename)
        p.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(str(p), "w") as zf:
            zf.writestr("aws-accelerator-config/global-config.yaml", "custom key content")

    mock_s3.download_file.side_effect = fake_download

    with patch("boto3.Session") as mock_session_cls:
        mock_session_cls.return_value.client.return_value = mock_s3
        path = run_download_config(target_dir=workspace_dir, force=True)

    mock_s3.download_file.assert_called_once_with(
        "my-test-bucket",
        "custom-prefix/custom-archive.zip",
        str(workspace_dir / "custom-archive.zip"),
    )
    assert path == workspace_dir / "aws-accelerator-config"
