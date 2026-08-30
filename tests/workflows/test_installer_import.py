"""Tests for installer import workflow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lza_workbench.errors import LzaError
from lza_workbench.workflows.installer_import import import_installer_workflow
from lza_workbench.workspace.config import load_workspace_config
from lza_workbench.workspace.schema import (
    AwsConfig,
    CustomerConfig,
    LzaConfig,
    WorkspaceConfig,
    WorkspaceState,
)
from lza_workbench.workspace.state import load_workspace_state, write_workspace_state


def _setup_test_workspace(ws_dir: Path) -> None:
    ws_dir.mkdir(parents=True, exist_ok=True)
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Import Customer", slug="import-customer"),
        aws=AwsConfig(profile="import-root", region="eu-west-1"),
        lza=LzaConfig(version="v1.15.5"),
    )
    (ws_dir / "lza-workspace.yaml").write_text(
        "customer:\n  name: Import Customer\n  slug: import-customer\n"
        "aws:\n  profile: import-root\n  region: eu-west-1\n",
        encoding="utf-8",
    )
    state = WorkspaceState.from_config(config)
    write_workspace_state(ws_dir, state)


def test_import_installer_workflow_success(tmp_path: Path) -> None:
    ws_dir = tmp_path / "ws"
    _setup_test_workspace(ws_dir)

    stack_id = (
        "arn:aws:cloudformation:eu-west-1:123456789012:stack/AWSAccelerator-InstallerStack/xyz"
    )
    mock_cfn = MagicMock()
    mock_cfn.describe_stacks.return_value = {
        "Stacks": [
            {
                "StackName": "AWSAccelerator-InstallerStack",
                "StackId": stack_id,
                "StackStatus": "UPDATE_COMPLETE",
                "Parameters": [
                    {
                        "ParameterKey": "ManagementAccountEmail",
                        "ParameterValue": "mgmt@example.com",
                    },
                    {
                        "ParameterKey": "AuditAccountEmail",
                        "ParameterValue": "audit@example.com",
                    },
                    {
                        "ParameterKey": "LogArchiveAccountEmail",
                        "ParameterValue": "log@example.com",
                    },
                    {"ParameterKey": "RepositorySource", "ParameterValue": "codecommit"},
                    {"ParameterKey": "RepositoryBranchName", "ParameterValue": "release/v1.15.5"},
                    {"ParameterKey": "ConfigurationRepositoryLocation", "ParameterValue": "s3"},
                    {"ParameterKey": "EnableApprovalStage", "ParameterValue": "Yes"},
                    {
                        "ParameterKey": "ApprovalStageNotifyEmailList",
                        "ParameterValue": "approver@example.com",
                    },
                ],
            }
        ]
    }

    mock_cp = MagicMock()
    mock_cp.get_pipeline_state.return_value = {
        "pipelineName": "AWSAccelerator-Installer",
        "stageStates": [],
    }

    def mock_get_client(service: str) -> MagicMock:
        if service == "cloudformation":
            return mock_cfn
        if service == "codepipeline":
            return mock_cp
        return MagicMock()

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client",
            side_effect=mock_get_client,
        ),
    ):
        mock_val.return_value = {
            "account": "123456789012",
            "arn": "arn:aws:iam::123456789012:user/admin",
        }
        result = import_installer_workflow(target_dir=ws_dir)

    assert result.stack_name == "AWSAccelerator-InstallerStack"
    assert result.cfn_status.exists is True
    assert result.config.installer.options.management_account_email == "mgmt@example.com"
    assert result.config.installer.options.approval_stage_notify_email_list == [
        "approver@example.com"
    ]
    assert result.config.configuration.repository.type == "s3"
    assert (
        result.config.configuration.repository.bucket
        == "aws-accelerator-config-123456789012-eu-west-1"
    )

    # Verify persisted to disk
    persisted_config = load_workspace_config(ws_dir)
    assert persisted_config.installer.options.management_account_email == "mgmt@example.com"
    persisted_state = load_workspace_state(ws_dir)
    assert persisted_state.installer_stack_id == stack_id


def test_import_installer_workflow_dry_run(tmp_path: Path) -> None:
    ws_dir = tmp_path / "ws-dry"
    _setup_test_workspace(ws_dir)

    stack_id = (
        "arn:aws:cloudformation:eu-west-1:123456789012:stack/AWSAccelerator-InstallerStack/xyz"
    )
    mock_cfn = MagicMock()
    mock_cfn.describe_stacks.return_value = {
        "Stacks": [
            {
                "StackName": "AWSAccelerator-InstallerStack",
                "StackId": stack_id,
                "StackStatus": "UPDATE_COMPLETE",
                "Parameters": [
                    {
                        "ParameterKey": "ManagementAccountEmail",
                        "ParameterValue": "mgmt@example.com",
                    },
                ],
            }
        ]
    }

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client",
            return_value=mock_cfn,
        ),
    ):
        mock_val.return_value = {
            "account": "123456789012",
            "arn": "arn:aws:iam::123456789012:user/admin",
        }
        result = import_installer_workflow(target_dir=ws_dir, dry_run=True)

    assert result.dry_run is True
    persisted_config = load_workspace_config(ws_dir)
    assert persisted_config.installer.options.management_account_email is None


def test_import_installer_workflow_missing_stack_raises(tmp_path: Path) -> None:
    from botocore.exceptions import ClientError

    ws_dir = tmp_path / "ws-missing"
    _setup_test_workspace(ws_dir)

    mock_cfn = MagicMock()
    mock_cfn.describe_stacks.side_effect = ClientError(
        {"Error": {"Code": "ValidationError", "Message": "Stack does not exist"}},
        "DescribeStacks",
    )

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client",
            return_value=mock_cfn,
        ),
    ):
        mock_val.return_value = {
            "account": "123456789012",
            "arn": "arn:aws:iam::123456789012:user/admin",
        }
        with pytest.raises(LzaError, match="was not found"):
            import_installer_workflow(target_dir=ws_dir)
