"""Tests for workspace import workflow."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from lza_workbench.configuration.git import init_git_repository, set_git_remote_url
from lza_workbench.configuration.templates import resolve_template_source
from lza_workbench.errors import LzaError
from lza_workbench.workflows.workspace_import import (
    WorkspaceImportResult,
    import_workspace_workflow,
    resolve_import_paths,
)
from lza_workbench.workspace.config import write_workspace_config
from lza_workbench.workspace.schema import (
    AwsConfig,
    CustomerConfig,
    LzaConfig,
    WorkspaceConfig,
)


def _copy_default_templates(config_dir: Path) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    template = resolve_template_source("default")
    for f in template.config_dir.glob("*.yaml"):
        shutil.copy(f, config_dir / f.name)


def test_resolve_import_paths_accepts_explicit_configuration_directory(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspace"
    config_dir = workspace_dir / "customer-config"
    _copy_default_templates(config_dir)

    resolved_workspace, resolved_config = resolve_import_paths(
        workspace_dir=workspace_dir,
        config_dir=config_dir,
    )

    assert resolved_workspace == workspace_dir
    assert resolved_config == config_dir


def test_import_workspace_workflow_dry_run(tmp_path: Path) -> None:
    ws_dir = tmp_path / "existing-ws"
    config_dir = ws_dir / "aws-accelerator-config"
    _copy_default_templates(config_dir)

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
    _copy_default_templates(config_dir)

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
    assert result.state.config_files_count is not None
    assert result.state.config_files_count > 0


def test_import_workspace_with_git_provenance(tmp_path: Path) -> None:
    ws_dir = tmp_path / "git-ws"
    config_dir = ws_dir / "aws-accelerator-config"
    _copy_default_templates(config_dir)

    # Initialize Git repository in config_dir with CodeCommit remote
    init_git_repository(config_dir)
    set_git_remote_url(
        config_dir,
        "origin",
        "https://git-codecommit.eu-west-1.amazonaws.com/v1/repos/customer-lza-config",
    )

    result = import_workspace_workflow(
        workspace_dir=ws_dir,
        customer_name="Git Customer",
        aws_profile="git-root",
        aws_region="eu-west-1",
        lza_version="v1.16.0",
        dry_run=False,
        skip_aws_check=True,
    )
    assert result.provenance is not None
    assert result.provenance.repo_type == "codecommit"
    assert result.provenance.repo_name == "customer-lza-config"
    assert result.config.configuration.template.source == "git"
    assert result.config.configuration.template.repository == "https://git-codecommit.eu-west-1.amazonaws.com/v1/repos/customer-lza-config"
    assert result.config.configuration.repository.type == "codecommit"
    assert result.config.configuration.repository.repository_name == "customer-lza-config"


def test_import_workspace_with_corrupted_yaml_fails(tmp_path: Path) -> None:
    ws_dir = tmp_path / "broken-yaml-ws"
    config_dir = ws_dir / "aws-accelerator-config"
    _copy_default_templates(config_dir)
    (config_dir / "network-config.yaml").write_text("invalid: [broken\n", encoding="utf-8")

    with pytest.raises(LzaError, match="Invalid YAML syntax in 'network-config.yaml'"):
        import_workspace_workflow(
            workspace_dir=ws_dir,
            customer_name="Broken Customer",
            skip_aws_check=True,
        )


def test_import_workspace_partial_metadata_requires_repair_or_force(tmp_path: Path) -> None:
    ws_dir = tmp_path / "partial-ws"
    config_dir = ws_dir / "aws-accelerator-config"
    _copy_default_templates(config_dir)

    config = WorkspaceConfig(
        customer=CustomerConfig(name="Partial Customer", slug="partial-customer"),
        aws=AwsConfig(profile="partial-root", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0"),
    )
    write_workspace_config(ws_dir, config)
    # state.json is deliberately not written

    with pytest.raises(LzaError, match="partial metadata.*--repair"):
        import_workspace_workflow(
            workspace_dir=ws_dir,
            customer_name="Partial Customer",
            skip_aws_check=True,
        )

    # Now with repair=True
    result = import_workspace_workflow(
        workspace_dir=ws_dir,
        customer_name="Partial Customer",
        repair=True,
        skip_aws_check=True,
    )
    assert result.repaired is True
    assert (ws_dir / ".lza" / "state.json").is_file()
