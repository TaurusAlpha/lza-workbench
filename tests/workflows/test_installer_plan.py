"""Tests for installer plan and init workflows."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from lza_workbench.aws.cloudformation import CfnDeploymentPlanResult
from lza_workbench.installer.planning import InstallerPlanResult
from lza_workbench.workflows.installer_init import initialize_installer_workflow
from lza_workbench.workflows.installer_plan import plan_installer_workflow
from lza_workbench.workspace.config import load_workspace_config, write_workspace_config
from lza_workbench.workspace.schema import (
    AwsConfig,
    CustomerConfig,
    LzaConfig,
    WorkspaceConfig,
    WorkspaceState,
)
from lza_workbench.workspace.state import write_workspace_state


def test_plan_installer_workflow_returns_structured_result(
    configured_workspace: Path,
) -> None:
    with patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val:
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        with patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client:
            mock_client.return_value = MagicMock()
            result = plan_installer_workflow(
                target_dir=configured_workspace,
                dry_run=True,
            )
            assert isinstance(result, InstallerPlanResult)
            assert result.workspace_dir == configured_workspace
            assert result.dry_run is True
            assert result.region == "eu-west-1"
            assert result.aws_identity is not None
            assert result.aws_identity["account"] == "123456789012"


def test_plan_installer_workflow_does_not_mutate_local_template(
    configured_workspace: Path,
) -> None:
    template_path = configured_workspace / "aws-accelerator-installer" / (
        "AWSAccelerator-InstallerStack.template"
    )
    template_path.write_text(
        """{
          "Mappings": {"Global": {"SendAnonymizedData": {"Data": "Yes"}}},
          "Parameters": {
            "ManagementAccountEmail": {"Type": "String"},
            "RepositorySource": {"Type": "String", "AllowedValues": ["codecommit"]}
          }
        }""",
        encoding="utf-8",
    )
    expected_content = template_path.read_text(encoding="utf-8")

    config = load_workspace_config(configured_workspace)
    config.installer.options.anonymous_data = False
    write_workspace_config(configured_workspace, config)

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        mock_client.return_value = MagicMock()
        plan_installer_workflow(target_dir=configured_workspace)

    assert template_path.read_text(encoding="utf-8") == expected_content


def test_plan_installer_workflow_marks_changed_template_for_update(
    configured_workspace: Path,
) -> None:
    state = WorkspaceState.from_config(load_workspace_config(configured_workspace))
    state.installer_template_digest = "outdated"
    write_workspace_state(configured_workspace, state)

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
        patch("lza_workbench.workflows.installer_plan.inspect_cloudformation_stack") as mock_cfn,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        mock_client.return_value = MagicMock()
        mock_cfn.return_value = CfnDeploymentPlanResult(
            stack_name="AWSAccelerator-InstallerStack",
            operation="NO_CHANGE",
            stack_status="UPDATE_COMPLETE",
            resolved_parameters={},
        )

        result = plan_installer_workflow(target_dir=configured_workspace)

    assert result.cloudformation_plan.operation == "UPDATE"


def test_installer_init_persists_new_template_defaults(tmp_path: Path) -> None:
    """Defaults from a newer template are retained for later deployments."""
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
        initialize_installer_workflow(target_dir=ws_dir)

    persisted = load_workspace_config(ws_dir)
    assert persisted.installer.template_parameters == {"NewDefault": "accepted"}


def test_installer_init_prompts_for_every_selected_template_parameter(tmp_path: Path) -> None:
    """Interactive initialization collects mandatory and optional template parameters."""
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
        initialize_installer_workflow(target_dir=ws_dir, prompter=prompter)

    assert prompts == [
        ("MandatoryNewParameter: Required setting", None),
        ("OptionalNewParameter: OptionalNewParameter", "template-default"),
    ]
    persisted = load_workspace_config(ws_dir)
    assert persisted.installer.template_parameters == {
        "MandatoryNewParameter": "mandatory-value",
        "OptionalNewParameter": "accepted-optional-value",
    }


def test_installer_init_resolves_branch_default_after_source_selection(tmp_path: Path) -> None:
    """The branch prompt follows the repository source selected earlier in the form."""
    ws_dir = tmp_path / "branch-default-ws"
    ws_dir.mkdir()
    (ws_dir / ".lza").mkdir()
    installer_dir = ws_dir / "aws-accelerator-installer"
    installer_dir.mkdir()
    (ws_dir / "aws-accelerator-config").mkdir()
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Branch Default", slug="branch-default"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0"),
    )
    config.installer.options.management_account_email = "mgmt@example.com"
    config.installer.options.log_archive_account_email = "log@example.com"
    config.installer.options.audit_account_email = "audit@example.com"
    config.installer.source_code.repository_type = "codecommit"
    write_workspace_config(ws_dir, config)
    write_workspace_state(ws_dir, WorkspaceState.from_config(config))
    (installer_dir / "AWSAccelerator-InstallerStack.template").write_text(
        """{"Parameters": {
          "RepositorySource": {"Type": "String"},
          "RepositoryBranchName": {"Type": "String"}
        }}""",
        encoding="utf-8",
    )
    prompts: list[tuple[str, str | None]] = []

    def prompter(label: str, default: str | None) -> str:
        prompts.append((label, default))
        return "github" if label.startswith("RepositorySource:") else default or ""

    initialize_installer_workflow(target_dir=ws_dir, prompter=prompter)

    assert prompts == [
        ("RepositorySource: RepositorySource", "codecommit"),
        ("RepositoryBranchName: RepositoryBranchName", "release/v1.16.0"),
    ]


def test_installer_init_skips_inapplicable_parameters(tmp_path: Path) -> None:
    """Parameters that are not applicable to the current sources are skipped during prompting."""
    ws_dir = tmp_path / "skip-params-ws"
    ws_dir.mkdir()
    (ws_dir / ".lza").mkdir()
    installer_dir = ws_dir / "aws-accelerator-installer"
    installer_dir.mkdir()
    (ws_dir / "aws-accelerator-config").mkdir()
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Skip Params", slug="skip-params"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0"),
    )
    config.installer.options.management_account_email = "mgmt@example.com"
    config.installer.options.log_archive_account_email = "log@example.com"
    config.installer.options.audit_account_email = "audit@example.com"
    config.installer.source_code.repository_type = "codecommit"
    config.configuration.repository.type = "s3"
    write_workspace_config(ws_dir, config)
    write_workspace_state(ws_dir, WorkspaceState.from_config(config))
    (installer_dir / "AWSAccelerator-InstallerStack.template").write_text(
        """{
          "Parameters": {
            "RepositorySource": {"Type": "String", "Description": "Source"},
            "RepositoryOwner": {"Type": "String", "Description": "Owner"},
            "EnableApprovalStage": {"Type": "String", "Description": "Approval"},
            "ApprovalStageNotifyEmailList": {"Type": "String", "Description": "Emails"},
            "ConfigurationRepositoryLocation": {"Type": "String", "Description": "Config Loc"},
            "UseExistingConfigRepo": {"Type": "String", "Description": "Use Existing"},
            "ConfigCodeConnectionArn": {"Type": "String", "Description": "CodeConn ARN"},
            "ExistingConfigRepositoryName": {"Type": "String", "Description": "Existing Repo"}
          }
        }""",
        encoding="utf-8",
    )
    prompts: list[tuple[str, str | None]] = []

    def prompter(label: str, default: str | None) -> str:
        prompts.append((label, default))
        if label.startswith("RepositorySource:"):
            return "codecommit"
        if label.startswith("EnableApprovalStage:"):
            return "No"
        if label.startswith("ConfigurationRepositoryLocation:"):
            return "s3"
        return default or ""

    initialize_installer_workflow(
        target_dir=ws_dir,
        accelerator_prefix="CustomPrefix",
        prompter=prompter,
    )

    # RepositoryOwner skipped because source is codecommit
    # ApprovalStageNotifyEmailList skipped because EnableApprovalStage is No
    # UseExistingConfigRepo, ConfigCodeConnectionArn, ExistingConfigRepositoryName
    # skipped because config is s3
    assert [p[0] for p in prompts] == [
        "RepositorySource: Source",
        "EnableApprovalStage: Approval",
        "ConfigurationRepositoryLocation: Config Loc",
    ]
    saved_config = load_workspace_config(ws_dir)
    assert saved_config.lza.accelerator_prefix == "CustomPrefix"
    assert saved_config.installer.options.enable_approval_stage is False



def test_installer_plan_github_secret_check(tmp_path: Path) -> None:
    """Plan workflow inspects Secrets Manager for GitHub token secret when source is github."""
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
        plan_res = plan_installer_workflow(target_dir=ws_dir, dry_run=True)

    assert plan_res.github_secret_warning is not None
    assert "accelerator/github-token" in plan_res.github_secret_warning


def test_installer_init_populates_s3_config_bucket(tmp_path: Path) -> None:
    """Installer initialization populates canonical S3 config bucket when type is s3."""
    ws_dir = tmp_path / "s3-config-ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / ".lza").mkdir(parents=True, exist_ok=True)
    (ws_dir / "aws-accelerator-config").mkdir(parents=True, exist_ok=True)

    config = WorkspaceConfig(
        customer=CustomerConfig(name="S3 Customer", slug="s3-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1", account_id="123456789012"),
        lza=LzaConfig(version="v1.16.0"),
    )
    config.configuration.repository.type = "s3"
    config.configuration.repository.bucket = None
    config.installer.options.management_account_email = "mgmt@example.com"
    config.installer.options.log_archive_account_email = "log@example.com"
    config.installer.options.audit_account_email = "audit@example.com"
    write_workspace_config(ws_dir, config)
    write_workspace_state(ws_dir, WorkspaceState.from_config(config))

    res = initialize_installer_workflow(target_dir=ws_dir)
    expected_bucket = "aws-accelerator-config-123456789012-us-east-1"
    assert res.config.configuration.repository.bucket == expected_bucket

    saved_config = load_workspace_config(ws_dir)
    assert saved_config.configuration.repository.bucket == expected_bucket

