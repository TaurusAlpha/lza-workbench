"""Tests for lza installer deploy command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer

from lza_workbench.aws.cloudformation import CfnDeploymentPlanResult, CfnStackStatusResult
from lza_workbench.aws.codecommit import CodeCommitPlanResult
from lza_workbench.commands.installer_deploy import run_installer_deploy
from lza_workbench.core.workspace import (
    AwsConfig,
    CustomerConfig,
    LzaConfig,
    WorkspaceConfig,
    WorkspaceState,
    load_workspace_state,
    write_workspace_config,
    write_workspace_state,
)


@pytest.fixture
def sample_workspace(tmp_path: Path) -> Path:
    """Create a sample workspace directory with valid lza-workspace.yaml."""
    ws_dir = tmp_path / "comm-it"
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / ".lza").mkdir(parents=True, exist_ok=True)
    (ws_dir / "aws-accelerator-installer").mkdir(parents=True, exist_ok=True)

    config = WorkspaceConfig(
        customer=CustomerConfig(name="Comm IT", slug="comm-it"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0", accelerator_prefix="AWSAccelerator"),
    )
    config.installer.source_code.repository_type = "codecommit"
    config.installer.source_code.repository_name = "aws-accelerator-codecommit"
    config.installer.source_code.branch = "release/v1.16.0"

    config.installer.options.management_account_email = "root@example.com"
    config.installer.options.log_archive_account_email = "log@example.com"
    config.installer.options.audit_account_email = "audit@example.com"

    write_workspace_config(ws_dir / "lza-workspace.yaml", config)
    write_workspace_state(ws_dir / ".lza" / "state.json", WorkspaceState.from_config(config))

    template_file = ws_dir / "aws-accelerator-installer" / "AWSAccelerator-InstallerStack.template"
    template_file.write_text(
        '{"Description": "Installer", "Parameters": {'
        '"ManagementAccountEmail": {"Type": "String"},'
        '"RepositorySource": {"Type": "String"}'
        "}}",
        encoding="utf-8",
    )

    return ws_dir


def test_missing_aws_profile_failure(tmp_path: Path) -> None:
    """Test that missing AWS profile in lza-workspace.yaml raises a BadParameter exception."""
    ws_dir = tmp_path / "no-aws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    config = WorkspaceConfig(
        customer=CustomerConfig(name="No AWS", slug="no-aws"),
        aws=AwsConfig(profile="", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0"),
    )
    write_workspace_config(ws_dir / "lza-workspace.yaml", config)

    with pytest.raises(typer.BadParameter, match="AWS profile is missing"):
        run_installer_deploy(target_dir=ws_dir)


def test_missing_required_params_failure(tmp_path: Path) -> None:
    """Test that missing required installer parameters stops deployment."""
    ws_dir = tmp_path / "incomplete"
    ws_dir.mkdir(parents=True, exist_ok=True)
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Incomplete", slug="incomplete"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0"),
    )
    write_workspace_config(ws_dir / "lza-workspace.yaml", config)

    with pytest.raises(typer.BadParameter, match="missing from lza-workspace.yaml"):
        run_installer_deploy(target_dir=ws_dir)


@patch("lza_workbench.commands.installer_deploy.AwsClientFactory")
def test_installer_deploy_dry_run(
    mock_factory_cls: MagicMock,
    sample_workspace: Path,
) -> None:
    """Test dry-run deployment does not mutate AWS resources or update state."""
    mock_factory = MagicMock()
    mock_factory_cls.return_value = mock_factory
    mock_factory.validate_identity.return_value = {
        "account": "123456789012",
        "arn": "arn:aws:iam::123456789012:user/admin",
        "user_id": "ADMIN",
    }

    run_installer_deploy(dry_run=True, force=True, target_dir=sample_workspace)

    state = load_workspace_state(sample_workspace / ".lza" / "state.json")
    assert state.installer_stack_id is None


@patch("lza_workbench.commands.installer_deploy.stream_cloudformation_stack_events")
@patch("lza_workbench.commands.installer_deploy.deploy_cloudformation_stack")
@patch("lza_workbench.commands.installer_deploy.inspect_cloudformation_stack")
@patch("lza_workbench.commands.installer_deploy.inspect_codecommit_repository")
@patch("lza_workbench.commands.installer_deploy.AwsClientFactory")
def test_installer_deploy_success(
    mock_factory_cls: MagicMock,
    mock_inspect_cc: MagicMock,
    mock_inspect_cfn: MagicMock,
    mock_deploy_cfn: MagicMock,
    mock_stream_cfn: MagicMock,
    sample_workspace: Path,
) -> None:
    """Test successful deployment updates workspace state correctly."""
    mock_factory = MagicMock()
    mock_factory_cls.return_value = mock_factory
    mock_factory.validate_identity.return_value = {
        "account": "123456789012",
        "arn": "arn:aws:iam::123456789012:user/admin",
        "user_id": "ADMIN",
    }

    mock_inspect_cc.return_value = CodeCommitPlanResult(
        repository_name="aws-accelerator-codecommit",
        branch_name="release/v1.16.0",
        status="INITIALIZED",
        creation_required=False,
        sync_required=False,
        official_repo_url="",
        official_version_ref="",
    )
    mock_inspect_cfn.return_value = CfnDeploymentPlanResult(
        stack_name="AWSAccelerator-InstallerStack",
        operation="CREATE",
        stack_status=None,
        resolved_parameters={},
    )
    mock_deploy_cfn.return_value = (
        "arn:aws:cloudformation:us-east-1:123456789012:stack/AWSAccelerator-InstallerStack/uuid"
    )
    mock_stream_cfn.return_value = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack",
        exists=True,
        stack_status="CREATE_COMPLETE",
        stack_id="arn:aws:cloudformation:us-east-1:123456789012:stack/AWSAccelerator-InstallerStack/uuid",
        outputs={"PipelineName": "AWSAccelerator-Pipeline"},
    )

    run_installer_deploy(force=True, target_dir=sample_workspace)

    state = load_workspace_state(sample_workspace / ".lza" / "state.json")
    assert state.installer_stack_status == "CREATE_COMPLETE"
    assert (
        state.installer_stack_id
        == "arn:aws:cloudformation:us-east-1:123456789012:stack/AWSAccelerator-InstallerStack/uuid"
    )
    assert state.management_account_id == "123456789012"
