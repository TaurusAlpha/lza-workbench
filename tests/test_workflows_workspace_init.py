"""Tests for workspace init workflow."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.workflows.workspace_init import (
    WorkspaceInitResult,
    init_workspace_workflow,
)


def test_init_workspace_workflow_dry_run(tmp_path: Path) -> None:
    target_dir = tmp_path / "acme-corp"
    result = init_workspace_workflow(
        customer_name="Acme Corp",
        workspace_dir=target_dir,
        aws_profile="acme-admin",
        aws_region="us-east-1",
        lza_version="v1.16.0",
        dry_run=True,
    )
    assert isinstance(result, WorkspaceInitResult)
    assert result.dry_run is True
    assert result.workspace_dir == target_dir
    assert result.config.customer.name == "Acme Corp"
    assert result.config.customer.slug == "acme-corp"
    assert not target_dir.exists()


def test_init_workspace_workflow_execution(tmp_path: Path) -> None:
    target_dir = tmp_path / "acme-corp"
    result = init_workspace_workflow(
        customer_name="Acme Corp",
        workspace_dir=target_dir,
        aws_profile="acme-admin",
        aws_region="us-east-1",
        lza_version="v1.16.0",
        dry_run=False,
    )
    assert isinstance(result, WorkspaceInitResult)
    assert result.dry_run is False
    assert (target_dir / "lza-workspace.yaml").is_file()
    assert (target_dir / ".lza" / "state.json").is_file()
    assert (target_dir / "aws-accelerator-installer").is_dir()
    assert not (target_dir / "aws-accelerator-config").exists()
