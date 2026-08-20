"""Tests for the status command suite (lza status, installer, config, pipeline)."""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from lza_workbench.aws.cloudformation import CfnStackStatusResult
from lza_workbench.aws.context import AwsExecutionContext
from lza_workbench.cli import app
from lza_workbench.cli.commands.status_config import (
    status_config_command as run_config_status,
)
from lza_workbench.cli.commands.status_pipeline import (
    status_pipeline_command as run_pipeline_status,
)
from lza_workbench.cli.commands.status_root import (
    status_root_command as run_root_status,
)
from lza_workbench.errors import LzaError
from lza_workbench.installer.status import (
    calculate_configuration_drift,
    calculate_state_alignment,
)
from lza_workbench.workflows.status_installer import (
    prepare_installer_status,
    sync_installer_config,
    sync_installer_state,
)
from lza_workbench.workspace.config import load_workspace_config
from lza_workbench.workspace.schema import (
    AwsConfig,
    CustomerConfig,
    WorkspaceConfig,
    WorkspaceState,
)
from lza_workbench.workspace.state import load_workspace_state

runner = CliRunner()


def test_sync_installer_state_raises_when_not_exists(tmp_path):
    state = WorkspaceState()
    cfn_status = CfnStackStatusResult(stack_name="AWSAccelerator-InstallerStack", exists=False)
    with pytest.raises(LzaError, match="Cannot synchronize state"):
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

    loaded_state = load_workspace_state(tmp_path)
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

    loaded_config = load_workspace_config(tmp_path)
    assert loaded_config.installer.options.management_account_email == "mgmt@example.com"


def test_sync_installer_config_accepts_codeconnection_repository(tmp_path):
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
    )
    cfn_status = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack",
        exists=True,
        deployed_parameters={"ConfigurationRepositoryLocation": "codeconnection"},
    )

    new_config = sync_installer_config(
        workspace_dir=tmp_path,
        config=config,
        cfn_status=cfn_status,
    )

    assert new_config.configuration.repository.type == "codeconnection"


def test_calculate_configuration_drift_returns_only_changed_parameters():
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
    )

    drift = calculate_configuration_drift(
        config,
        {
            "RepositorySource": "github",
            "RepositoryOwner": "awslabs",
            "RepositoryName": "landing-zone-accelerator-on-aws",
            "RepositoryBranchName": "release/v1.15.5",
            "EnableApprovalStage": "Yes",
        },
    )

    assert drift["EnableApprovalStage"] == ("Yes", "No")
    assert "RepositorySource" not in drift


def test_calculate_state_alignment_compares_stack_and_version_metadata():
    state = WorkspaceState(
        installer_stack_id="stack-id",
        installer_stack_status="CREATE_COMPLETE",
        installer_template_version="v1.15.5",
    )

    aligned = calculate_state_alignment(
        state,
        stack_id="stack-id",
        stack_status="CREATE_COMPLETE",
        deployed_version="release/v1.15.5",
    )
    stale = calculate_state_alignment(
        state,
        stack_id="stack-id",
        stack_status="UPDATE_COMPLETE",
        deployed_version="v1.15.5",
    )

    assert aligned.in_sync is True
    assert stale.in_sync is False


def test_prepare_installer_status_separates_comparisons_from_rendering(tmp_path):
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
    )
    state = WorkspaceState(
        installer_stack_status="CREATE_COMPLETE",
        installer_template_version="v1.15.5",
    )
    cfn_status = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack",
        exists=True,
        stack_status="CREATE_COMPLETE",
        deployed_parameters={"RepositoryBranchName": "release/v1.15.5"},
    )

    result = prepare_installer_status(
        workspace_dir=tmp_path,
        config=config,
        state=state,
        profile="test-profile",
        region="us-east-1",
        aws_identity=None,
        aws_error="No credentials",
        cfn_status=cfn_status,
    )

    assert result.deployed_version == "v1.15.5"
    assert result.state_alignment is not None
    assert result.state_alignment.in_sync is True


def test_pipeline_status_displays_separate_execution_ids(tmp_path, monkeypatch):
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
    )
    state = WorkspaceState(
        installer_pipeline_execution_id="installer-execution",
        config_pipeline_execution_id="config-execution",
    )
    mock_ctx = MagicMock(workspace_dir=tmp_path, config=config, state=state)
    aws_context = AwsExecutionContext(
        region="us-east-1", factory=MagicMock(), identity=None, error="No credentials"
    )
    monkeypatch.setattr(
        "lza_workbench.workflows.status_pipeline.load_workspace_context",
        lambda *_args, **_kwargs: mock_ctx,
    )
    monkeypatch.setattr(
        "lza_workbench.workflows.status_pipeline.resolve_aws_execution_context",
        lambda *args, **kwargs: aws_context,
    )

    result = runner.invoke(app, ["status", "pipeline"])

    assert result.exit_code == 0
    assert "installer-execution" in result.output
    assert "config-execution" in result.output


@patch("lza_workbench.workflows.status_root.get_cloudformation_stack_status")
@patch("lza_workbench.workflows.status_root.resolve_aws_execution_context")
def test_run_root_status(mock_resolve_context, mock_get_cfn, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lza-workspace.yaml").write_text(
        "customer:\n  name: Test\n  slug: test\naws:\n  profile: default\n  region: us-east-1\n"
    )
    mock_factory = MagicMock()
    mock_resolve_context.return_value = AwsExecutionContext(
        region="us-east-1",
        factory=mock_factory,
        identity={"account": "123456789012", "arn": "arn:aws:iam::123:user/test"},
        error=None,
    )
    mock_get_cfn.return_value = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack", exists=True, stack_status="CREATE_COMPLETE"
    )

    run_root_status(target_dir=tmp_path)


@patch("lza_workbench.workflows.status_config.load_workspace_context")
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


@patch("lza_workbench.workflows.status_pipeline.resolve_aws_execution_context")
def test_run_pipeline_status(mock_resolve_context, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lza-workspace.yaml").write_text(
        "customer:\n  name: Test\n  slug: test\naws:\n  profile: default\n  region: us-east-1\n"
    )
    mock_factory = MagicMock()
    mock_resolve_context.return_value = AwsExecutionContext(
        region="us-east-1",
        factory=mock_factory,
        identity={"account": "123456789012", "arn": "arn:aws:iam::123:user/test"},
        error=None,
    )

    run_pipeline_status(target_dir=tmp_path)


@patch("lza_workbench.workflows.status_installer.get_cloudformation_stack_status")
@patch("lza_workbench.workflows.status_installer.resolve_aws_execution_context")
@patch("lza_workbench.workflows.status_root.resolve_aws_execution_context")
@patch("lza_workbench.workflows.status_pipeline.resolve_aws_execution_context")
def test_cli_status_commands(
    mock_pipeline_context,
    mock_main_context,
    mock_installer_context,
    mock_get_cfn,
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lza-workspace.yaml").write_text(
        "customer:\n  name: Test\n  slug: test\naws:\n  profile: default\n  region: us-east-1\n"
    )
    mock_factory = MagicMock()
    aws_context = AwsExecutionContext(
        region="us-east-1",
        factory=mock_factory,
        identity={"account": "123456789012", "arn": "arn:aws:iam::123:user/test"},
        error=None,
    )
    mock_pipeline_context.return_value = aws_context
    mock_main_context.return_value = aws_context
    mock_installer_context.return_value = aws_context
    mock_get_cfn.return_value = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack", exists=True, stack_status="CREATE_COMPLETE"
    )

    res_root = runner.invoke(app, ["status"])
    assert res_root.exit_code == 0

    res_installer = runner.invoke(app, ["status", "installer"])
    assert res_installer.exit_code == 0
    assert "Config Pipeline Name" not in res_installer.output
    assert "Config Pipeline ARN" not in res_installer.output
    assert "Stack Outputs" not in res_installer.output
    assert "No stack outputs available" not in res_installer.output
    assert "Installer Pipeline Status" in res_installer.output

    # Test lza installer status alias
    res_installer_alias = runner.invoke(app, ["installer", "status"])
    assert res_installer_alias.exit_code == 0
    assert "Config Pipeline Name" not in res_installer_alias.output
    assert "Config Pipeline ARN" not in res_installer_alias.output
    assert "Stack Outputs" not in res_installer_alias.output
    assert "No stack outputs available" not in res_installer_alias.output
    assert "Installer Pipeline Status" in res_installer_alias.output

    res_config = runner.invoke(app, ["status", "config"])
    assert res_config.exit_code == 0

    res_pipeline = runner.invoke(app, ["status", "pipeline"])
    assert res_pipeline.exit_code == 0
