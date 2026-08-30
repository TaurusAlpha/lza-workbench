"""Tests for CLI installer import commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from lza_workbench.cli.main import app
from lza_workbench.workspace.schema import (
    AwsConfig,
    CustomerConfig,
    LzaConfig,
    WorkspaceConfig,
    WorkspaceState,
)
from lza_workbench.workspace.state import write_workspace_state


def _setup_test_workspace(ws_dir: Path) -> None:
    ws_dir.mkdir(parents=True, exist_ok=True)
    config = WorkspaceConfig(
        customer=CustomerConfig(name="CLI Cust", slug="cli-cust"),
        aws=AwsConfig(profile="cli-root", region="eu-west-1"),
        lza=LzaConfig(version="v1.15.5"),
    )
    (ws_dir / "lza-workspace.yaml").write_text(
        "customer:\n  name: CLI Cust\n  slug: cli-cust\n"
        "aws:\n  profile: cli-root\n  region: eu-west-1\n",
        encoding="utf-8",
    )
    state = WorkspaceState.from_config(config)
    write_workspace_state(ws_dir, state)


def test_cli_installer_import_success(
    tmp_path: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _setup_test_workspace(tmp_path)

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
                        "ParameterKey": "ConfigurationRepositoryLocation",
                        "ParameterValue": "s3",
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
        result = cli_runner.invoke(app, ["installer", "import"])

    assert result.exit_code == 0
    assert "Successfully imported live AWS installer deployment" in result.output
    assert "AWSAccelerator-InstallerStack" in result.output


def test_cli_installer_import_with_custom_stack_name(
    tmp_path: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _setup_test_workspace(tmp_path)

    stack_id = "arn:aws:cloudformation:eu-west-1:123456789012:stack/Custom-InstallerStack/xyz"
    mock_cfn = MagicMock()
    mock_cfn.describe_stacks.return_value = {
        "Stacks": [
            {
                "StackName": "Custom-InstallerStack",
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
        result = cli_runner.invoke(
            app,
            ["installer", "import", "--installer-stack-name", "Custom-InstallerStack"],
        )

    assert result.exit_code == 0
    assert "Successfully imported live AWS installer deployment" in result.output
    assert "Custom-InstallerStack" in result.output


def test_cli_installer_import_dry_run(
    tmp_path: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _setup_test_workspace(tmp_path)

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
        result = cli_runner.invoke(app, ["installer", "import", "--dry-run"])

    assert result.exit_code == 0
    assert "Dry run" in result.output
