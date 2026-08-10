"""Tests for the status command suite (lza status, installer, config, pipeline)."""

from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from lza_workbench.aws.cloudformation import CfnStackStatusResult
from lza_workbench.cli import app
from lza_workbench.commands.status import (
    run_config_status,
    run_pipeline_status,
    run_root_status,
)
from lza_workbench.commands.status.status_installer import (
    extract_version_from_branch,
    normalize_version,
    sync_installer_config,
    sync_installer_state,
)
from lza_workbench.core.workspace import (
    AwsConfig,
    CustomerConfig,
    WorkspaceConfig,
    WorkspaceState,
    load_workspace_config,
    load_workspace_state,
)

runner = CliRunner()


def test_extract_and_normalize_version():
    assert extract_version_from_branch("") == "Unknown"
    assert extract_version_from_branch("release/v1.15.5") == "v1.15.5"
    assert extract_version_from_branch("main") == "latest"
    assert extract_version_from_branch("1.15.5") == "v1.15.5"

    assert normalize_version("1.15.5") == "v1.15.5"
    assert normalize_version("v1.15.5") == "v1.15.5"
    assert normalize_version("latest") == "latest"


def test_sync_installer_state_raises_when_not_exists(tmp_path):
    state = WorkspaceState()
    cfn_status = CfnStackStatusResult(stack_name="AWSAccelerator-InstallerStack", exists=False)
    with pytest.raises(typer.BadParameter, match="Cannot synchronize state"):
        sync_installer_state(
            workspace_dir=tmp_path,
            state=state,
            cfn_status=cfn_status,
            deployed_version="v1.15.5",
        )


def test_sync_installer_state_success(tmp_path):
    state = WorkspaceState()
    cfn_status = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack",
        exists=True,
        stack_id="arn:aws:cloudformation:us-east-1:123:stack/test/123",
        stack_status="CREATE_COMPLETE",
    )
    new_state = sync_installer_state(
        workspace_dir=tmp_path,
        state=state,
        cfn_status=cfn_status,
        deployed_version="v1.15.5",
    )
    assert new_state.installer_stack_id == cfn_status.stack_id
    assert new_state.installer_stack_status == "CREATE_COMPLETE"
    assert new_state.installer_template_version == "v1.15.5"

    loaded_state = load_workspace_state(tmp_path / ".lza" / "state.json")
    assert loaded_state.installer_stack_id == cfn_status.stack_id


def test_sync_installer_config_success(tmp_path):
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
    )
    cfn_status = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack",
        exists=True,
        deployed_parameters={
            "RepositorySource": "codecommit",
            "RepositoryOwner": "aws",
            "RepositoryName": "aws-accelerator",
            "RepositoryBranchName": "release/v1.15.5",
            "ManagementAccountEmail": "mgmt@example.com",
            "EnableApprovalStage": "Yes",
        },
    )
    new_config = sync_installer_config(
        workspace_dir=tmp_path,
        config=config,
        cfn_status=cfn_status,
    )
    assert new_config.installer.source_code.repository_type == "codecommit"
    assert new_config.installer.options.management_account_email == "mgmt@example.com"
    assert new_config.installer.options.enable_approval_stage is True

    loaded_config = load_workspace_config(tmp_path / "lza-workspace.yaml")
    assert loaded_config.installer.options.management_account_email == "mgmt@example.com"


@patch("lza_workbench.commands.status.status_main.get_cloudformation_stack_status")
@patch("lza_workbench.commands.status.status_main.AwsClientFactory")
def test_run_root_status(mock_factory_cls, mock_get_cfn, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lza-workspace.yaml").write_text(
        "customer:\n  name: Test\n  slug: test\naws:\n  profile: default\n  region: us-east-1\n"
    )
    mock_factory = MagicMock()
    mock_factory.validate_identity.return_value = {
        "account": "123456789012",
        "arn": "arn:aws:iam::123:user/test",
    }
    mock_factory_cls.return_value = mock_factory
    mock_get_cfn.return_value = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack", exists=True, stack_status="CREATE_COMPLETE"
    )

    run_root_status(target_dir=tmp_path)


@patch("lza_workbench.commands.status.status_config.load_workspace_context")
def test_run_config_status(mock_load_ctx, tmp_path):
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
    )
    state = WorkspaceState()
    mock_ctx = MagicMock()
    mock_ctx.workspace_dir = tmp_path
    mock_ctx.config = config
    mock_ctx.state = state
    mock_load_ctx.return_value = mock_ctx

    run_config_status(target_dir=tmp_path)


@patch("lza_workbench.commands.status.status_pipeline.AwsClientFactory")
def test_run_pipeline_status(mock_factory_cls, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lza-workspace.yaml").write_text(
        "customer:\n  name: Test\n  slug: test\naws:\n  profile: default\n  region: us-east-1\n"
    )
    mock_factory = MagicMock()
    mock_factory.validate_identity.return_value = {
        "account": "123456789012",
        "arn": "arn:aws:iam::123:user/test",
    }
    mock_factory_cls.return_value = mock_factory

    run_pipeline_status(target_dir=tmp_path)


@patch("lza_workbench.commands.status.status_installer.get_cloudformation_stack_status")
@patch("lza_workbench.commands.status.status_installer.AwsClientFactory")
def test_cli_status_commands(mock_factory_cls, mock_get_cfn, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lza-workspace.yaml").write_text(
        "customer:\n  name: Test\n  slug: test\naws:\n  profile: default\n  region: us-east-1\n"
    )
    mock_factory = MagicMock()
    mock_factory.validate_identity.return_value = {
        "account": "123456789012",
        "arn": "arn:aws:iam::123:user/test",
    }
    mock_factory_cls.return_value = mock_factory
    mock_get_cfn.return_value = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack", exists=True, stack_status="CREATE_COMPLETE"
    )

    res_root = runner.invoke(app, ["status"])
    assert res_root.exit_code == 0

    res_installer = runner.invoke(app, ["status", "installer"])
    assert res_installer.exit_code == 0

    # Test lza installer status alias
    res_installer_alias = runner.invoke(app, ["installer", "status"])
    assert res_installer_alias.exit_code == 0

    res_config = runner.invoke(app, ["status", "config"])
    assert res_config.exit_code == 0

    res_pipeline = runner.invoke(app, ["status", "pipeline"])
    assert res_pipeline.exit_code == 0
