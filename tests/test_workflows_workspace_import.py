"""Tests for workspace import workflow."""

from __future__ import annotations

import shutil
from pathlib import Path

from lza_workbench.configuration.templates import resolve_template_source
from lza_workbench.workflows.workspace_import import (
    WorkspaceImportResult,
    import_workspace_workflow,
)


def test_import_workspace_workflow_dry_run(tmp_path: Path) -> None:
    ws_dir = tmp_path / "existing-ws"
    config_dir = ws_dir / "aws-accelerator-config"
    config_dir.mkdir(parents=True)
    template = resolve_template_source("default")
    for f in template.config_dir.glob("*.yaml"):
        shutil.copy(f, config_dir / f.name)

    result = import_workspace_workflow(
        workspace_dir=ws_dir,
        customer_name="Existing Customer",
        aws_profile="existing-root",
        aws_region="us-east-1",
        lza_version="v1.16.0",
        dry_run=True,
        skip_aws_check=True,
    )
    assert isinstance(result, WorkspaceImportResult)
    assert result.dry_run is True
    assert result.workspace_dir == ws_dir
    assert result.config.customer.name == "Existing Customer"
    assert not (ws_dir / "lza-workspace.yaml").exists()


def test_import_workspace_workflow_execution(tmp_path: Path) -> None:
    ws_dir = tmp_path / "existing-ws"
    config_dir = ws_dir / "aws-accelerator-config"
    config_dir.mkdir(parents=True)
    template = resolve_template_source("default")
    for f in template.config_dir.glob("*.yaml"):
        shutil.copy(f, config_dir / f.name)

    result = import_workspace_workflow(
        workspace_dir=ws_dir,
        customer_name="Existing Customer",
        aws_profile="existing-root",
        aws_region="us-east-1",
        lza_version="v1.16.0",
        dry_run=False,
        skip_aws_check=True,
    )
    assert isinstance(result, WorkspaceImportResult)
    assert result.dry_run is False
    assert (ws_dir / "lza-workspace.yaml").is_file()
    assert (ws_dir / ".lza" / "state.json").is_file()
