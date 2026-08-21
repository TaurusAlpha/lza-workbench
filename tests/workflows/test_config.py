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


def test_download_configuration_workflow_dry_run(configured_workspace: Path) -> None:
    result = download_configuration_workflow(
        target_dir=configured_workspace,
        dry_run=True,
    )
    assert isinstance(result, ConfigDownloadResult)
    assert result.dry_run is True
    assert result.workspace_dir == configured_workspace
    assert result.s3_key == "zipped/aws-accelerator-config.zip"


def test_upload_configuration_workflow_dry_run(configured_workspace: Path) -> None:
    result = upload_configuration_workflow(
        target_dir=configured_workspace,
        dry_run=True,
    )
    assert isinstance(result, ConfigUploadResult)
    assert result.dry_run is True
    assert result.workspace_dir == configured_workspace


def test_upload_configuration_workflow_missing_directory(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(LzaError, match="Command must be run inside an LZA workspace"):
        upload_configuration_workflow(target_dir=empty_dir)
