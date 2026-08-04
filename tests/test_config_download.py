"""Tests for lza config download command."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer

from lza_workbench.cli import main
from lza_workbench.commands.config_download import (
    run_download_config,
)
from lza_workbench.commands.workspace_init import run_init
from lza_workbench.core.workspace import (
    load_workspace_config,
    load_workspace_state,
    resolve_workspace_dir,
    write_workspace_config,
)


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
    return target


def test_resolve_workspace_dir_fails_outside_workspace(tmp_path: Path) -> None:
    with pytest.raises(typer.BadParameter, match="must be run inside an LZA workspace directory"):
        resolve_workspace_dir(tmp_path)


def test_resolve_workspace_dir_finds_workspace_from_subdir(workspace_dir: Path) -> None:
    subdir = workspace_dir / "aws-accelerator-config"
    assert resolve_workspace_dir(subdir) == workspace_dir


def test_run_download_config_requires_bucket(workspace_dir: Path) -> None:
    with pytest.raises(typer.BadParameter, match="No S3 bucket configured"):
        run_download_config(target_dir=workspace_dir, interactive=False)


def test_run_download_config_dry_run(workspace_dir: Path) -> None:
    config_file = workspace_dir / "lza-workspace.yaml"
    cfg = load_workspace_config(config_file)
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(config_file, cfg)

    path = run_download_config(target_dir=workspace_dir, dry_run=True)
    assert path == workspace_dir / "aws-accelerator-config"


def test_run_download_config_force_required(workspace_dir: Path) -> None:
    config_file = workspace_dir / "lza-workspace.yaml"
    cfg = load_workspace_config(config_file)
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(config_file, cfg)

    with pytest.raises(typer.BadParameter, match="not empty"):
        run_download_config(target_dir=workspace_dir, force=False, interactive=False)


def test_run_download_config_success(workspace_dir: Path) -> None:
    config_file = workspace_dir / "lza-workspace.yaml"
    cfg = load_workspace_config(config_file)
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(config_file, cfg)

    config_dir = workspace_dir / "aws-accelerator-config"
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

    state = load_workspace_state(workspace_dir / ".lza" / "state.json")
    assert state.config_downloaded_at is not None
    assert state.config_artifact_sha256 is not None
    assert state.config_files_count == 2
    assert state.config_last_diff_summary == {"added": 1, "modified": 1, "removed": 1}


def test_run_download_config_without_extract(workspace_dir: Path) -> None:
    config_file = workspace_dir / "lza-workspace.yaml"
    cfg = load_workspace_config(config_file)
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(config_file, cfg)

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


def test_cli_config_download_command(workspace_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_file = workspace_dir / "lza-workspace.yaml"
    cfg = load_workspace_config(config_file)
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(config_file, cfg)

    monkeypatch.chdir(workspace_dir)
    exit_code = main(["config", "download", "--dry-run"])
    assert exit_code == 0
