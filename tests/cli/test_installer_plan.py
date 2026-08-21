"""Tests for lza installer plan and init CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from lza_workbench.aws.secrets_manager import inspect_github_secret_token
from lza_workbench.cli.commands.installer_plan import (
    installer_init_command as run_installer_init,
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

    config.installer.options.management_account_email = "root@example.com"
    config.installer.options.log_archive_account_email = "log@example.com"
    config.installer.options.audit_account_email = "audit@example.com"

    write_workspace_config(ws_dir, config)
    write_workspace_state(ws_dir, WorkspaceState.from_config(config))

    template_file = ws_dir / "aws-accelerator-installer" / "AWSAccelerator-InstallerStack.template"
    template_file.write_text(
        '{"Description": "Installer", "Parameters": {'
        '"ManagementAccountEmail": {"Type": "String", "Description": "Email"},'
        '"RepositorySource": {"Type": "String", "AllowedValues": ["github", "codecommit"]}'
        "}}",
        encoding="utf-8",
    )

    return ws_dir


def test_installer_init_succeeds_with_core_defaults(tmp_path: Path) -> None:
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

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        mock_client.return_value = MagicMock()
        run_installer_init(
            dry_run=True,
            no_save=True,
            target_dir=ws_dir,
            interactive=False,
            management_account_email="mgmt@example.com",
            log_archive_account_email="log@example.com",
            audit_account_email="audit@example.com",
        )


def test_installer_init_updates_workspace_config(tmp_path: Path) -> None:
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

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        mock_client.return_value = MagicMock()
        run_installer_init(
            target_dir=ws_dir,
            management_account_email="mgmt@prompted.com",
            log_archive_account_email="log@prompted.com",
            audit_account_email="audit@prompted.com",
            dry_run=False,
            no_save=False,
            interactive=False,
        )

    updated_config = load_workspace_config(ws_dir)
    assert updated_config.installer.options.management_account_email == "mgmt@prompted.com"
    assert updated_config.installer.options.log_archive_account_email == "log@prompted.com"
    assert updated_config.installer.options.audit_account_email == "audit@prompted.com"


def test_installer_init_non_interactive_rejects_missing_emails(tmp_path: Path) -> None:
    ws_dir = tmp_path / "non-interactive-ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / ".lza").mkdir(parents=True, exist_ok=True)
    (ws_dir / "aws-accelerator-config").mkdir(parents=True, exist_ok=True)

    config = WorkspaceConfig(
        customer=CustomerConfig(name="Non Interactive", slug="non-interactive"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0"),
    )
    write_workspace_config(ws_dir, config)
    write_workspace_state(ws_dir, WorkspaceState.from_config(config))

    with pytest.raises(LzaError, match="required configuration is missing"):
        run_installer_init(target_dir=ws_dir, interactive=False, dry_run=True, no_save=True)


def test_installer_init_no_save(sample_workspace: Path) -> None:
    with patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val:
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        with patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client:
            mock_client.return_value = MagicMock()
            run_installer_init(
                dry_run=False,
                no_save=True,
                target_dir=sample_workspace,
                interactive=False,
            )

    config = load_workspace_config(sample_workspace)
    assert config.installer.options.management_account_email == "root@example.com"


def test_installer_plan_prepares_result_before_rendering(sample_workspace: Path) -> None:
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
        patch(
            "lza_workbench.cli.commands.installer_plan.render_installer_plan_report"
        ) as mock_render,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        mock_client.return_value = MagicMock()

        run_installer_plan(
            dry_run=False,
            target_dir=sample_workspace,
        )

    rendered_plan = mock_render.call_args.args[0]
    assert isinstance(rendered_plan, InstallerPlanResult)
    assert rendered_plan.workspace_dir == sample_workspace


def test_installer_plan_codecommit_missing(sample_workspace: Path) -> None:
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
                target_dir=sample_workspace,
            )

        mock_cc.get_repository.assert_called_once_with(repositoryName="aws-accelerator-codecommit")
        mock_cfn.describe_stacks.assert_called_once_with(StackName="AWSAccelerator-InstallerStack")


def test_installer_plan_cfn_update_detected(sample_workspace: Path) -> None:
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
                target_dir=sample_workspace,
            )

        mock_cfn.describe_stacks.assert_called_once_with(StackName="AWSAccelerator-InstallerStack")


def test_installer_init_imported_workspace_succeeds(tmp_path: Path) -> None:
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

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        mock_client.return_value = MagicMock()
        run_installer_init(
            target_dir=ws_dir,
            management_account_email="mgmt@example.com",
            log_archive_account_email="log@example.com",
            audit_account_email="audit@example.com",
            dry_run=True,
            no_save=True,
            interactive=False,
        )


def test_installer_plan_github_secret_check_requires_exact_name() -> None:
    mock_sm = MagicMock()
    mock_sm.describe_secret.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException"}}, "DescribeSecret"
    )

    warning = inspect_github_secret_token(mock_sm)

    assert warning is not None
    mock_sm.describe_secret.assert_called_once_with(SecretId="accelerator/github-token")
