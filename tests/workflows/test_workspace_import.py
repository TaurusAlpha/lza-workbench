"""Tests for workspace import workflow."""

from __future__ import annotations

import shutil
from pathlib import Path

from lza_workbench.configuration.templates import REQUIRED_TEMPLATE_FILES, resolve_template_source
from lza_workbench.workflows.workspace_import import (
    WorkspaceImportResult,
    import_workspace_workflow,
    resolve_import_paths,
)


def _write_required_files(config_dir: Path) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    for filename in REQUIRED_TEMPLATE_FILES:
        (config_dir / filename).write_text("{}\n", encoding="utf-8")


def test_resolve_import_paths_accepts_explicit_configuration_directory(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspace"
    config_dir = workspace_dir / "customer-config"
    _write_required_files(config_dir)

    resolved_workspace, resolved_config = resolve_import_paths(
        workspace_dir=workspace_dir,
        config_dir=config_dir,
    )

    assert resolved_workspace == workspace_dir
    assert resolved_config == config_dir


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
