"""Tests for workspace init workflow."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.workflows.workspace_init import (
    WorkspaceInitResult,
    init_workspace_workflow,
)
from lza_workbench.workspace.schema import WorkspaceConfig


def test_workspace_config_defaults() -> None:
    config = WorkspaceConfig.create(
        customer_name="Example Customer",
        customer_slug="example-customer",
        aws_profile="example-root",
        aws_region="eu-west-1",
        lza_version="v1.15.5",
    )

    assert config.configuration.template.source == "packaged"
    assert config.configuration.template.name == "default"
    assert config.configuration.local_path == "aws-accelerator-config"
    assert config.installer.local_path == "aws-accelerator-installer"


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


def test_init_workspace_workflow_role_arn(tmp_path: Path) -> None:
    target_dir = tmp_path / "acme-corp"
    result = init_workspace_workflow(
        customer_name="Acme Corp",
        workspace_dir=target_dir,
        aws_auth_type="role_arn",
        aws_role_arn="arn:aws:iam::123456789012:role/DeployRole",
        aws_region="eu-west-1",
        lza_version="v1.16.0",
        dry_run=False,
    )
    assert result.config.aws.role_arn == "arn:aws:iam::123456789012:role/DeployRole"
    assert result.config.aws.profile is None

