"""Tests for lza installer plan command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from lza_workbench.aws.secrets_manager import inspect_github_secret_token
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


def test_installer_plan_succeeds_with_core_defaults(tmp_path: Path) -> None:
    """Test that lza installer plan succeeds using core workspace defaults."""
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
        run_installer_plan(
            dry_run=True,
            no_save=True,
            target_dir=ws_dir,
            interactive=False,
            management_account_email="mgmt@example.com",
            log_archive_account_email="log@example.com",
            audit_account_email="audit@example.com",
        )


def test_installer_plan_prompts_and_updates_workspace_config(tmp_path: Path) -> None:
    """Installer plan prompts/receives missing required parameters and updates config."""
    ws_dir = tmp_path / "prompt-ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / ".lza").mkdir(parents=True, exist_ok=True)
    (ws_dir / "aws-accelerator-installer").mkdir(parents=True, exist_ok=True)
    (ws_dir / "aws-accelerator-config").mkdir(parents=True, exist_ok=True)

    config = WorkspaceConfig(
        customer=CustomerConfig(name="Prompt Customer", slug="prompt-customer"),
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
        run_installer_plan(
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


def test_installer_plan_non_interactive_rejects_missing_emails(tmp_path: Path) -> None:
    """Non-interactive planning rejects incomplete installer configuration."""
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
        run_installer_plan(target_dir=ws_dir, interactive=False, dry_run=True, no_save=True)


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
                interactive=False,
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

        run_installer_plan(
            dry_run=False,
            no_save=True,
            target_dir=sample_workspace,
            interactive=False,
        )

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
                interactive=False,
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
                interactive=False,
            )

        mock_cfn.describe_stacks.assert_called_once_with(StackName="AWSAccelerator-InstallerStack")


def test_installer_plan_imported_workspace_succeeds(tmp_path: Path) -> None:
    """Imported workspace loads and executes installer plan using core workspace parameters."""
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
        run_installer_plan(
            target_dir=ws_dir,
            management_account_email="mgmt@example.com",
            log_archive_account_email="log@example.com",
            audit_account_email="audit@example.com",
            dry_run=True,
            no_save=True,
            interactive=False,
        )


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


def test_build_installer_cfn_parameters_conditional_filtering() -> None:
    """Parameters are conditionally collected/cleared based on deployment options."""
    from lza_workbench.installer.parameters import build_installer_cfn_parameters

    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test", slug="test"),
        aws=AwsConfig(profile="default", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0"),
    )
    config.installer.options.enable_approval_stage = False
    config.installer.options.approval_stage_notify_email_list = ["test@example.com"]
    config.installer.source_code.repository_type = "codecommit"
    config.configuration.repository.type = "s3"

    schema = {"CustomParam": {"Default": "CustomValue"}}
    params = build_installer_cfn_parameters(config, schema=schema)

    assert params["ApprovalStageNotifyEmailList"] == ""
    assert params["RepositoryOwner"] == ""
    assert params["UseExistingConfigRepo"] == "No"
    assert params["ConfigCodeConnectionArn"] == ""
    assert params["CustomParam"] == "CustomValue"


def test_installer_plan_persists_new_template_defaults(tmp_path: Path) -> None:
    """Defaults from a newer template are retained for later deployments."""
    from lza_workbench.workflows.installer_plan import plan_installer_workflow

    ws_dir = tmp_path / "template-default-ws"
    ws_dir.mkdir()
    (ws_dir / ".lza").mkdir()
    installer_dir = ws_dir / "aws-accelerator-installer"
    installer_dir.mkdir()
    (ws_dir / "aws-accelerator-config").mkdir()
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Template Defaults", slug="template-defaults"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0"),
    )
    config.installer.options.management_account_email = "mgmt@example.com"
    config.installer.options.log_archive_account_email = "log@example.com"
    config.installer.options.audit_account_email = "audit@example.com"
    write_workspace_config(ws_dir, config)
    write_workspace_state(ws_dir, WorkspaceState.from_config(config))
    (installer_dir / "AWSAccelerator-InstallerStack.template").write_text(
        '{"Parameters": {"NewDefault": {"Default": "accepted"}}}', encoding="utf-8"
    )

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        mock_client.return_value = MagicMock()
        plan_installer_workflow(target_dir=ws_dir)

    persisted = load_workspace_config(ws_dir)
    assert persisted.installer.template_parameters == {"NewDefault": "accepted"}


def test_installer_plan_prompts_for_every_selected_template_parameter(tmp_path: Path) -> None:
    """Interactive planning collects mandatory and optional template parameters."""
    from lza_workbench.workflows.installer_plan import plan_installer_workflow

    ws_dir = tmp_path / "template-prompts-ws"
    ws_dir.mkdir()
    (ws_dir / ".lza").mkdir()
    installer_dir = ws_dir / "aws-accelerator-installer"
    installer_dir.mkdir()
    (ws_dir / "aws-accelerator-config").mkdir()
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Template Prompts", slug="template-prompts"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0"),
    )
    config.installer.options.management_account_email = "mgmt@example.com"
    config.installer.options.log_archive_account_email = "log@example.com"
    config.installer.options.audit_account_email = "audit@example.com"
    write_workspace_config(ws_dir, config)
    write_workspace_state(ws_dir, WorkspaceState.from_config(config))
    (installer_dir / "AWSAccelerator-InstallerStack.template").write_text(
        """{
          "Parameters": {
            "MandatoryNewParameter": {"Type": "String", "Description": "Required setting"},
            "OptionalNewParameter": {"Type": "String", "Default": "template-default"}
          }
        }""",
        encoding="utf-8",
    )
    prompts: list[tuple[str, str | None]] = []

    def prompter(label: str, default: str | None) -> str:
        prompts.append((label, default))
        return "mandatory-value" if default is None else "accepted-optional-value"

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        mock_client.return_value = MagicMock()
        plan_installer_workflow(target_dir=ws_dir, prompter=prompter)

    assert prompts == [
        ("MandatoryNewParameter: Required setting", None),
        ("OptionalNewParameter: OptionalNewParameter", "template-default"),
    ]
    persisted = load_workspace_config(ws_dir)
    assert persisted.installer.template_parameters == {
        "MandatoryNewParameter": "mandatory-value",
        "OptionalNewParameter": "accepted-optional-value",
    }


def test_installer_plan_github_secret_check(tmp_path: Path) -> None:
    """Plan workflow inspects Secrets Manager for GitHub token secret when source is github."""
    from lza_workbench.workflows.installer_plan import plan_installer_workflow

    ws_dir = tmp_path / "github-ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / ".lza").mkdir(parents=True, exist_ok=True)
    (ws_dir / "aws-accelerator-config").mkdir(parents=True, exist_ok=True)

    config = WorkspaceConfig(
        customer=CustomerConfig(name="GitHub Customer", slug="github-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0"),
    )
    config.installer.source_code.repository_type = "github"
    config.installer.options.management_account_email = "mgmt@example.com"
    config.installer.options.log_archive_account_email = "log@example.com"
    config.installer.options.audit_account_email = "audit@example.com"
    write_workspace_config(ws_dir, config)
    write_workspace_state(ws_dir, WorkspaceState.from_config(config))

    mock_sm = MagicMock()
    err_resp = {"Error": {"Code": "ResourceNotFoundException"}}
    mock_sm.describe_secret.side_effect = ClientError(err_resp, "DescribeSecret")

    def client_side_effect(service_name: str) -> MagicMock:
        if service_name == "secretsmanager":
            return mock_sm
        return MagicMock()

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client",
            side_effect=client_side_effect,
        ),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        plan_res = plan_installer_workflow(target_dir=ws_dir, dry_run=True, no_save=True)

    assert plan_res.github_secret_warning is not None
    assert "accelerator/github-token" in plan_res.github_secret_warning


def test_installer_plan_github_secret_check_requires_exact_name(tmp_path: Path) -> None:
    """Only the documented GitHub token secret name satisfies the prerequisite."""

    mock_sm = MagicMock()
    mock_sm.describe_secret.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException"}}, "DescribeSecret"
    )

    warning = inspect_github_secret_token(mock_sm)

    assert warning is not None
    mock_sm.describe_secret.assert_called_once_with(SecretId="accelerator/github-token")
