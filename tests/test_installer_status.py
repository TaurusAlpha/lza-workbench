"""Tests for lza installer status command."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from lza_workbench.cli import main
from lza_workbench.commands.installer_status import (
    extract_version_from_branch,
    normalize_version,
    run_installer_status,
)
from lza_workbench.core.workspace import (
    AwsConfig,
    CustomerConfig,
    LzaConfig,
    WorkspaceConfig,
    WorkspaceState,
    write_workspace_config,
    write_workspace_state,
)


@pytest.fixture
def status_workspace(tmp_path: Path) -> Path:
    """Create a sample workspace directory with config and state for status testing."""
    ws_dir = tmp_path / "status-ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / ".lza").mkdir(parents=True, exist_ok=True)

    config = WorkspaceConfig(
        customer=CustomerConfig(name="Status Test", slug="status-ws"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0", accelerator_prefix="AWSAccelerator"),
    )
    config.installer.source_code.repository_type = "codecommit"
    config.installer.source_code.repository_name = "aws-accelerator-codecommit"
    config.installer.source_code.branch = "release/v1.16.0"

    write_workspace_config(ws_dir / "lza-workspace.yaml", config)

    state = WorkspaceState.from_config(config)
    state.installer_stack_id = (
        "arn:aws:cloudformation:us-east-1:123456789012:stack/AWSAccelerator-InstallerStack/uuid"
    )
    state.installer_stack_status = "CREATE_COMPLETE"
    state.installer_template_version = "v1.16.0"
    state.installer_downloaded_at = datetime.now(UTC)
    write_workspace_state(ws_dir / ".lza" / "state.json", state)

    return ws_dir


def test_extract_version_from_branch() -> None:
    """Test helper for parsing version strings from Git branch names."""
    assert extract_version_from_branch("release/v1.15.5") == "v1.15.5"
    assert extract_version_from_branch("release/1.15.5") == "v1.15.5"
    assert extract_version_from_branch("v1.16.0") == "v1.16.0"
    assert extract_version_from_branch("main") == "latest"
    assert extract_version_from_branch("") == "Unknown"


def test_normalize_version() -> None:
    """Test helper for version string normalization."""
    assert normalize_version("v1.16.0") == "v1.16.0"
    assert normalize_version("1.16.0") == "v1.16.0"
    assert normalize_version("latest") == "latest"
    assert normalize_version("") == "latest"


def test_installer_status_not_deployed(status_workspace: Path) -> None:
    """Test installer status when stack is not deployed on AWS."""
    with patch(
        "lza_workbench.aws.client_factory.AwsClientFactory.validate_identity"
    ) as mock_val:
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}

        mock_cfn = MagicMock()
        err_cfn = {"Error": {"Code": "ValidationError", "Message": "Stack does not exist"}}
        mock_cfn.describe_stacks.side_effect = ClientError(err_cfn, "DescribeStacks")

        with patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client",
            return_value=mock_cfn,
        ):
            run_installer_status(target_dir=status_workspace)

        mock_cfn.describe_stacks.assert_called_once_with(StackName="AWSAccelerator-InstallerStack")


def test_installer_status_deployed_no_drift(status_workspace: Path) -> None:
    """Test installer status when stack exists with matching parameters."""
    with patch(
        "lza_workbench.aws.client_factory.AwsClientFactory.validate_identity"
    ) as mock_val:
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}

        mock_cfn = MagicMock()
        mock_cfn.describe_stacks.return_value = {
            "Stacks": [
                {
                    "StackName": "AWSAccelerator-InstallerStack",
                    "StackStatus": "CREATE_COMPLETE",
                    "StackId": "arn:aws:cloudformation:us-east-1:123456789012:stack/AWSAccelerator-InstallerStack/uuid",
                    "CreationTime": "2026-08-04T10:00:00Z",
                    "Parameters": [
                        {"ParameterKey": "RepositorySource", "ParameterValue": "codecommit"},
                        {"ParameterKey": "RepositoryOwner", "ParameterValue": "awslabs"},
                        {
                            "ParameterKey": "RepositoryName",
                            "ParameterValue": "aws-accelerator-codecommit",
                        },
                        {
                            "ParameterKey": "RepositoryBranchName",
                            "ParameterValue": "release/v1.16.0",
                        },
                        {"ParameterKey": "AcceleratorPrefix", "ParameterValue": "AWSAccelerator"},
                        {"ParameterKey": "EnableApprovalStage", "ParameterValue": "No"},
                        {"ParameterKey": "ApprovalStageNotifyEmailList", "ParameterValue": ""},
                        {"ParameterKey": "ManagementAccountEmail", "ParameterValue": ""},
                        {"ParameterKey": "LogArchiveAccountEmail", "ParameterValue": ""},
                        {"ParameterKey": "AuditAccountEmail", "ParameterValue": ""},
                        {"ParameterKey": "ControlTowerEnabled", "ParameterValue": "Yes"},
                        {"ParameterKey": "ConfigurationRepositoryLocation", "ParameterValue": "s3"},
                        {"ParameterKey": "UseExistingConfigRepo", "ParameterValue": "No"},
                        {"ParameterKey": "ConfigCodeConnectionArn", "ParameterValue": ""},
                        {"ParameterKey": "ExistingConfigRepositoryOwner", "ParameterValue": ""},
                        {"ParameterKey": "ExistingConfigRepositoryName", "ParameterValue": ""},
                        {
                            "ParameterKey": "ExistingConfigRepositoryBranchName",
                            "ParameterValue": "",
                        },
                        {"ParameterKey": "EnableDiagnosticsPack", "ParameterValue": "No"},
                    ],
                    "Outputs": [
                        {
                            "OutputKey": "PipelineName",
                            "OutputValue": "AWSAccelerator-Pipeline",
                            "Description": "LZA Pipeline Name",
                        }
                    ],
                }
            ]
        }

        with patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client",
            return_value=mock_cfn,
        ):
            run_installer_status(target_dir=status_workspace)

        mock_cfn.describe_stacks.assert_called_once_with(StackName="AWSAccelerator-InstallerStack")


def test_installer_status_deployed_with_drift(status_workspace: Path) -> None:
    """Test installer status when parameter drift and version mismatch exist."""
    with patch(
        "lza_workbench.aws.client_factory.AwsClientFactory.validate_identity"
    ) as mock_val:
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}

        mock_cfn = MagicMock()
        mock_cfn.describe_stacks.return_value = {
            "Stacks": [
                {
                    "StackName": "AWSAccelerator-InstallerStack",
                    "StackStatus": "UPDATE_COMPLETE",
                    "StackId": "arn:aws:cloudformation:us-east-1:123456789012:stack/AWSAccelerator-InstallerStack/uuid",
                    "Parameters": [
                        {"ParameterKey": "RepositorySource", "ParameterValue": "github"},
                        {"ParameterKey": "RepositoryOwner", "ParameterValue": "awslabs"},
                        {
                            "ParameterKey": "RepositoryName",
                            "ParameterValue": "landing-zone-accelerator-on-aws",
                        },
                        {
                            "ParameterKey": "RepositoryBranchName",
                            "ParameterValue": "release/v1.15.0",
                        },
                    ],
                    "Outputs": [],
                }
            ]
        }

        with patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client",
            return_value=mock_cfn,
        ):
            run_installer_status(target_dir=status_workspace)

        mock_cfn.describe_stacks.assert_called_once_with(StackName="AWSAccelerator-InstallerStack")


def test_cli_installer_status_command(
    status_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test invoking lza installer status via the main CLI entrypoint."""
    monkeypatch.chdir(status_workspace)

    with patch(
        "lza_workbench.aws.client_factory.AwsClientFactory.validate_identity"
    ) as mock_val:
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        mock_cfn = MagicMock()
        err_cfn = {"Error": {"Code": "ValidationError", "Message": "Stack does not exist"}}
        mock_cfn.describe_stacks.side_effect = ClientError(err_cfn, "DescribeStacks")

        with patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client",
            return_value=mock_cfn,
        ):
            exit_code = main(["installer", "status"])
            assert exit_code == 0
