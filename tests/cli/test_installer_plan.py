"""Tests for lza installer plan and init CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from typer.testing import CliRunner

from lza_workbench.aws.secrets_manager import inspect_github_secret_token
from lza_workbench.cli import app
from lza_workbench.workspace.config import load_workspace_config, write_workspace_config
from lza_workbench.workspace.schema import (
    AwsConfig,
    CustomerConfig,
    LzaConfig,
    WorkspaceConfig,
    WorkspaceState,
)
from lza_workbench.workspace.state import write_workspace_state


def test_installer_init_succeeds_with_core_defaults(
    tmp_path: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws_dir = tmp_path / "incomplete-ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / ".lza").mkdir(parents=True, exist_ok=True)
    (ws_dir / "aws-accelerator-installer").mkdir(parents=True, exist_ok=True)
    (ws_dir / "aws-accelerator-config").mkdir(parents=True, exist_ok=True)

    config = WorkspaceConfig(
        customer=CustomerConfig(name="Incomplete", slug="incomplete"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0"),
    )
    write_workspace_config(ws_dir, config)
    write_workspace_state(ws_dir, WorkspaceState.from_config(config))

    template_file = ws_dir / "aws-accelerator-installer" / "AWSAccelerator-InstallerStack.template"
    template_file.write_text('{"Description": "Installer", "Parameters": {}}', encoding="utf-8")

    monkeypatch.chdir(ws_dir)
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        mock_client.return_value = MagicMock()
        result = cli_runner.invoke(
            app,
            [
                "installer",
                "init",
                "--dry-run",
                "--no-save",
                "--management-account-email",
                "mgmt@example.com",
                "--log-archive-account-email",
                "log@example.com",
                "--audit-account-email",
                "audit@example.com",
            ],
        )

    assert result.exit_code == 0
    assert "Dry run" in result.output


def test_installer_init_updates_workspace_config(
    tmp_path: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws_dir = tmp_path / "prompt-ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / ".lza").mkdir(parents=True, exist_ok=True)
    (ws_dir / "aws-accelerator-installer").mkdir(parents=True, exist_ok=True)
    (ws_dir / "aws-accelerator-config").mkdir(parents=True, exist_ok=True)

    config = WorkspaceConfig(
        customer=CustomerConfig(name="Prompt Customer", slug="prompt-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
        lza=LzaConfig(version="1.16.0"),
    )
    write_workspace_config(ws_dir, config)
    write_workspace_state(ws_dir, WorkspaceState.from_config(config))

    monkeypatch.chdir(ws_dir)
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        mock_client.return_value = MagicMock()
        result = cli_runner.invoke(
            app,
            [
                "installer",
                "init",
                "--management-account-email",
                "mgmt@prompted.com",
                "--log-archive-account-email",
                "log@prompted.com",
                "--audit-account-email",
                "audit@prompted.com",
            ],
        )

    assert result.exit_code == 0
    updated_config = load_workspace_config(ws_dir)
    assert updated_config.installer.options.management_account_email == "mgmt@prompted.com"
    assert updated_config.installer.options.log_archive_account_email == "log@prompted.com"
    assert updated_config.installer.options.audit_account_email == "audit@prompted.com"


def test_installer_init_no_save(
    configured_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(configured_workspace)
    with patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val:
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        with patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client:
            mock_client.return_value = MagicMock()
            result = cli_runner.invoke(
                app,
                [
                    "installer",
                    "init",
                    "--no-save",
                    "--management-account-email",
                    "changed@example.com",
                    "--log-archive-account-email",
                    "changed-log@example.com",
                    "--audit-account-email",
                    "changed-audit@example.com",
                ],
            )

    assert result.exit_code == 0
    config = load_workspace_config(configured_workspace)
    assert config.installer.options.management_account_email == "mgmt@example.com"


def test_installer_plan_codecommit_missing(
    configured_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(configured_workspace)
    with patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val:
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}

        mock_cc = MagicMock()
        mock_cfn = MagicMock()

        err_response = {"Error": {"Code": "RepositoryDoesNotExistException"}}
        mock_cc.get_repository.side_effect = ClientError(err_response, "GetRepository")

        err_cfn = {"Error": {"Code": "ValidationError", "Message": "Stack does not exist"}}
        mock_cfn.describe_stacks.side_effect = ClientError(err_cfn, "DescribeStacks")

        def client_side_effect(service_name: str) -> MagicMock:
            if service_name == "codecommit":
                return mock_cc
            if service_name == "cloudformation":
                return mock_cfn
            return MagicMock()

        with patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client",
            side_effect=client_side_effect,
        ):
            result = cli_runner.invoke(app, ["installer", "plan"])

        assert result.exit_code == 0
        mock_cc.get_repository.assert_called_once_with(repositoryName="aws-accelerator-codecommit")
        mock_cfn.describe_stacks.assert_called_once_with(StackName="AWSAccelerator-InstallerStack")


def test_installer_plan_cfn_update_detected(
    configured_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(configured_workspace)
    with patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val:
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}

        mock_cc = MagicMock()
        mock_cfn = MagicMock()

        mock_cc.get_repository.return_value = {
            "repositoryMetadata": {"repositoryName": "aws-accelerator-codecommit"}
        }
        mock_cc.get_branch.return_value = {"branch": {"branchName": "release/v1.16.0"}}

        mock_cfn.describe_stacks.return_value = {
            "Stacks": [
                {
                    "StackName": "AWSAccelerator-InstallerStack",
                    "StackStatus": "CREATE_COMPLETE",
                    "Parameters": [
                        {
                            "ParameterKey": "ManagementAccountEmail",
                            "ParameterValue": "old-root@example.com",
                        },
                        {"ParameterKey": "RepositorySource", "ParameterValue": "codecommit"},
                    ],
                }
            ]
        }

        def client_side_effect(service_name: str) -> MagicMock:
            if service_name == "codecommit":
                return mock_cc
            if service_name == "cloudformation":
                return mock_cfn
            return MagicMock()

        with patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client",
            side_effect=client_side_effect,
        ):
            result = cli_runner.invoke(app, ["installer", "plan"])

        assert result.exit_code == 0
        mock_cfn.describe_stacks.assert_called_once_with(StackName="AWSAccelerator-InstallerStack")


def test_installer_plan_github_secret_check_requires_exact_name() -> None:
    mock_sm = MagicMock()
    mock_sm.describe_secret.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException"}}, "DescribeSecret"
    )

    warning = inspect_github_secret_token(mock_sm)

    assert warning is not None
    mock_sm.describe_secret.assert_called_once_with(SecretId="accelerator/github-token")
