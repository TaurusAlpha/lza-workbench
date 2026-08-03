"""Tests for lza config download command."""

from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer

from lza_workbench.cli import main
from lza_workbench.commands.download_config import (
    resolve_workspace_dir,
    run_download_config,
)
from lza_workbench.commands.init_workspace import run_init
from lza_workbench.core.workspace import (
    load_workspace_config,
    load_workspace_state,
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

    git_dir = workspace_dir / "aws-accelerator-config" / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    def fake_download(bucket: str, key: str, filename: str) -> None:
        p = Path(filename)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("downloaded content", encoding="utf-8")

    mock_boto3 = MagicMock()
    mock_s3 = MagicMock()
    mock_boto3.Session.return_value.client.return_value = mock_s3
    mock_paginator = MagicMock()
    mock_s3.get_paginator.return_value = mock_paginator
    mock_paginator.paginate.return_value = [{"Contents": [{"Key": "global-config.yaml"}]}]
    mock_s3.download_file.side_effect = fake_download

    with patch.dict("sys.modules", {"boto3": mock_boto3, "botocore.exceptions": MagicMock()}):
        path = run_download_config(target_dir=workspace_dir, force=True)

    assert path == workspace_dir / "aws-accelerator-config"
    assert (path / "global-config.yaml").read_text(encoding="utf-8") == "downloaded content"
    assert (git_dir / "HEAD").is_file()

    state = load_workspace_state(workspace_dir / ".lza" / "state.json")
    assert state.config_downloaded_at is not None


def test_run_download_config_with_extract(workspace_dir: Path) -> None:
    config_file = workspace_dir / "lza-workspace.yaml"
    cfg = load_workspace_config(config_file)
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(config_file, cfg)

    def fake_download(bucket: str, key: str, filename: str) -> None:
        p = Path(filename)
        p.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(str(p), "w") as zf:
            zf.writestr("global-config.yaml", "extracted config content")

    mock_boto3 = MagicMock()
    mock_s3 = MagicMock()
    mock_boto3.Session.return_value.client.return_value = mock_s3
    mock_paginator = MagicMock()
    mock_s3.get_paginator.return_value = mock_paginator
    mock_paginator.paginate.return_value = [{"Contents": [{"Key": "config.zip"}]}]
    mock_s3.download_file.side_effect = fake_download

    with patch.dict("sys.modules", {"boto3": mock_boto3, "botocore.exceptions": MagicMock()}):
        path = run_download_config(target_dir=workspace_dir, force=True, extract=True)

    assert (path / "global-config.yaml").read_text(encoding="utf-8") == "extracted config content"
    assert not (path / "config.zip").exists()


def test_cli_config_download_command(workspace_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_file = workspace_dir / "lza-workspace.yaml"
    cfg = load_workspace_config(config_file)
    cfg.configuration.repository.bucket = "my-test-bucket"
    write_workspace_config(config_file, cfg)

    monkeypatch.chdir(workspace_dir)
    exit_code = main(["config", "download", "--dry-run"])
    assert exit_code == 0
