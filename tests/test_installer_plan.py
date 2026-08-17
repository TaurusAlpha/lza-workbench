"""Tests for lza installer plan command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from lza_workbench.cli.commands.installer_deploy import (
    installer_deploy_command as run_installer_deploy,
)
from lza_workbench.cli.commands.installer_plan import (
    installer_plan_command as run_installer_plan,
)
from lza_workbench.errors import LzaError
from lza_workbench.installer.planning import InstallerPlanResult
from lza_workbench.workspace.config import load_workspace_config, write_workspace_config
from lza_workbench.workspace.schema import (
    AwsConfig,
    CustomerConfig,
    LzaConfig,
    WorkspaceConfig,
    WorkspaceState,
)
from lza_workbench.workspace.state import write_workspace_state


@pytest.fixture
def sample_workspace(tmp_path: Path) -> Path:
    """Create a sample workspace directory with valid lza-workspace.yaml."""
    ws_dir = tmp_path / "comm-it"
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / ".lza").mkdir(parents=True, exist_ok=True)
    (ws_dir / "aws-accelerator-installer").mkdir(parents=True, exist_ok=True)
    (ws_dir / "aws-accelerator-config").mkdir(parents=True, exist_ok=True)

    config = WorkspaceConfig(
        customer=CustomerConfig(name="Comm IT", slug="comm-it"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0", accelerator_prefix="AWSAccelerator"),
    )
    config.installer.source_code.repository_type = "codecommit"
    config.installer.source_code.repository_name = "aws-accelerator-codecommit"
    config.installer.source_code.branch = "release/v1.16.0"

    # Set mandatory emails
    config.installer.options.management_account_email = "root@example.com"
    config.installer.options.log_archive_account_email = "log@example.com"
    config.installer.options.audit_account_email = "audit@example.com"

    write_workspace_config(ws_dir, config)
    write_workspace_state(ws_dir, WorkspaceState.from_config(config))

    # Create dummy template file
    template_file = ws_dir / "aws-accelerator-installer" / "AWSAccelerator-InstallerStack.template"
    template_file.write_text(
        '{"Description": "Installer", "Parameters": {'
        '"ManagementAccountEmail": {"Type": "String", "Description": "Email"},'
        '"RepositorySource": {"Type": "String", "AllowedValues": ["github", "codecommit"]}'
        "}}",
        encoding="utf-8",
    )

    return ws_dir


def test_missing_parameters_graceful_failure(tmp_path: Path) -> None:
    """Test that missing required parameters fail gracefully with a clear error."""
    ws_dir = tmp_path / "incomplete-ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / ".lza").mkdir(parents=True, exist_ok=True)
    (ws_dir / "aws-accelerator-installer").mkdir(parents=True, exist_ok=True)

    config = WorkspaceConfig(
        customer=CustomerConfig(name="Incomplete", slug="incomplete"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0"),
    )
    write_workspace_config(ws_dir, config)
    write_workspace_state(ws_dir, WorkspaceState.from_config(config))

    template_file = ws_dir / "aws-accelerator-installer" / "AWSAccelerator-InstallerStack.template"
    template_file.write_text('{"Description": "Installer", "Parameters": {}}', encoding="utf-8")

    with pytest.raises(LzaError) as exc_info:
        run_installer_plan(
            dry_run=False,
            no_save=False,
            target_dir=ws_dir,
        )

    assert "missing" in str(exc_info.value).lower()


def test_installer_plan_no_save(sample_workspace: Path) -> None:
    """Test that --no-save executes plan successfully without errors."""
    with patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val:
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        with patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client:
            mock_client.return_value = MagicMock()
            run_installer_plan(
                dry_run=False,
                no_save=True,
                target_dir=sample_workspace,
            )

    config = load_workspace_config(sample_workspace)
    assert config.installer.options.management_account_email == "root@example.com"


def test_installer_plan_prepares_result_before_rendering(sample_workspace: Path) -> None:
    """The renderer receives a prepared result rather than command workflow inputs."""
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
        patch(
            "lza_workbench.cli.commands.installer_plan.render_installer_plan_report"
        ) as mock_render,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        mock_client.return_value = MagicMock()

        run_installer_plan(dry_run=False, no_save=True, target_dir=sample_workspace)

    rendered_plan = mock_render.call_args.args[0]
    assert isinstance(rendered_plan, InstallerPlanResult)
    assert rendered_plan.workspace_dir == sample_workspace


def test_installer_plan_codecommit_missing(sample_workspace: Path) -> None:
    """Test CodeCommit planning when repository is missing in AWS."""
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
            run_installer_plan(
                dry_run=False,
                no_save=False,
                target_dir=sample_workspace,
            )

        mock_cc.get_repository.assert_called_once_with(repositoryName="aws-accelerator-codecommit")
        mock_cfn.describe_stacks.assert_called_once_with(StackName="AWSAccelerator-InstallerStack")


def test_installer_plan_cfn_update_detected(sample_workspace: Path) -> None:
    """Test CloudFormation planning when stack exists with differing parameters (UPDATE)."""
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
            run_installer_plan(
                dry_run=False,
                no_save=False,
                target_dir=sample_workspace,
            )

        mock_cfn.describe_stacks.assert_called_once_with(StackName="AWSAccelerator-InstallerStack")


def test_installer_plan_imported_workspace_reports_missing_fields(tmp_path: Path) -> None:
    """Imported workspace loads and reports specific missing installer fields during plan."""
    ws_dir = tmp_path / "imported-ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / ".lza").mkdir(parents=True, exist_ok=True)
    (ws_dir / "aws-accelerator-config").mkdir(parents=True, exist_ok=True)

    config = WorkspaceConfig(
        customer=CustomerConfig(name="Imported Customer", slug="imported-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0"),
    )
    write_workspace_config(ws_dir, config)
    write_workspace_state(ws_dir, WorkspaceState.from_config(config))

    with pytest.raises(
        LzaError, match="required parameter\\(s\\) missing from lza-workspace\\.yaml"
    ):
        run_installer_plan(target_dir=ws_dir)


def test_installer_deploy_refuses_imported_workspace(tmp_path: Path) -> None:
    """Installer deploy strictly enforces CONFIGURED readiness and refuses IMPORTED workspace."""
    ws_dir = tmp_path / "imported-ws-deploy"
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / ".lza").mkdir(parents=True, exist_ok=True)
    (ws_dir / "aws-accelerator-config").mkdir(parents=True, exist_ok=True)

    config = WorkspaceConfig(
        customer=CustomerConfig(name="Imported Customer", slug="imported-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0"),
    )
    write_workspace_config(ws_dir, config)
    write_workspace_state(ws_dir, WorkspaceState.from_config(config))

    with pytest.raises(LzaError, match="missing required installer configuration parameters"):
        run_installer_deploy(target_dir=ws_dir)

