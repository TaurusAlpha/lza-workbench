"""Tests for configuration workflows."""

from __future__ import annotations

from pathlib import Path

import pytest

from lza_workbench.errors import LzaError
from lza_workbench.workflows.config_download import (
    ConfigDownloadResult,
    download_configuration_workflow,
)
from lza_workbench.workflows.config_upload import (
    ConfigUploadResult,
    upload_configuration_workflow,
)
from lza_workbench.workflows.workspace_init import init_workspace_workflow


@pytest.fixture
def initialized_workspace(tmp_path: Path) -> Path:
    ws_dir = tmp_path / "acme"
    init_workspace_workflow(
        customer_name="Acme",
        workspace_dir=ws_dir,
        aws_profile="dev-profile",
        aws_region="us-east-1",
        skip_aws_check=True,
        dry_run=False,
        force=False,
    )
    from lza_workbench.workspace.config import load_workspace_config, write_workspace_config

    config = load_workspace_config(ws_dir)
    config.configuration.repository.type = "s3"
    config.configuration.repository.bucket = "test-bucket"
    write_workspace_config(ws_dir, config)
    return ws_dir


def test_download_configuration_workflow_dry_run(initialized_workspace: Path) -> None:
    result = download_configuration_workflow(
        target_dir=initialized_workspace,
        dry_run=True,
    )
    assert isinstance(result, ConfigDownloadResult)
    assert result.dry_run is True
    assert result.workspace_dir == initialized_workspace
    assert result.s3_key == "zipped/aws-accelerator-config.zip"


def test_upload_configuration_workflow_dry_run(initialized_workspace: Path) -> None:
    result = upload_configuration_workflow(
        target_dir=initialized_workspace,
        dry_run=True,
    )
    assert isinstance(result, ConfigUploadResult)
    assert result.dry_run is True
    assert result.workspace_dir == initialized_workspace


def test_upload_configuration_workflow_missing_directory(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(LzaError, match="Command must be run inside an LZA workspace"):
        upload_configuration_workflow(target_dir=empty_dir)
