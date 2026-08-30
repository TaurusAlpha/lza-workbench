"""Tests for installer CloudFormation parameter assembly and mapping."""

from __future__ import annotations

from lza_workbench.installer.parameters import (
    apply_installer_parameter,
    build_installer_cfn_parameters,
    is_installer_parameter_applicable,
)
from lza_workbench.workspace.schema import (
    AwsConfig,
    CustomerConfig,
    LzaConfig,
    WorkspaceConfig,
)


def test_build_installer_cfn_parameters_conditional_filtering() -> None:
    """Parameters are conditionally collected/cleared based on deployment options."""
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


def test_collecting_repository_branch_persists_the_resolved_default() -> None:
    """Applying empty branch resolves and sets the default version branch."""
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
    )
    config.lza.version = "1.16.0"

    apply_installer_parameter(config, "RepositoryBranchName", "")

    assert config.installer.source_code.branch == "release/v1.16.0"


def test_is_installer_parameter_applicable_github_and_s3() -> None:
    """GitHub source and S3 config repo filter out inapplicable parameters."""
    config = WorkspaceConfig(
        customer=CustomerConfig(name="GitHub S3", slug="github-s3"),
        aws=AwsConfig(profile="default", region="us-east-1"),
    )
    config.installer.source_code.repository_type = "github"
    config.configuration.repository.type = "s3"
    config.installer.options.enable_approval_stage = False

    assert is_installer_parameter_applicable(config, "RepositorySource") is True
    assert is_installer_parameter_applicable(config, "RepositoryOwner") is True
    assert is_installer_parameter_applicable(config, "RepositoryName") is True
    assert is_installer_parameter_applicable(config, "RepositoryBranchName") is True
    assert is_installer_parameter_applicable(config, "EnableApprovalStage") is True
    assert is_installer_parameter_applicable(config, "ApprovalStageNotifyEmailList") is False
    assert is_installer_parameter_applicable(config, "ManagementAccountEmail") is True
    assert is_installer_parameter_applicable(config, "ConfigurationRepositoryLocation") is True
    assert is_installer_parameter_applicable(config, "UseExistingConfigRepo") is False
    assert is_installer_parameter_applicable(config, "ConfigCodeConnectionArn") is False
    assert is_installer_parameter_applicable(config, "ExistingConfigRepositoryOwner") is False
    assert is_installer_parameter_applicable(config, "ExistingConfigRepositoryName") is False
    assert is_installer_parameter_applicable(config, "ExistingConfigRepositoryBranchName") is False


def test_is_installer_parameter_applicable_codecommit_and_codeconnection() -> None:
    """CodeCommit source and CodeConnection config repo with use_existing=True."""
    config = WorkspaceConfig(
        customer=CustomerConfig(name="CC CC", slug="cc-cc"),
        aws=AwsConfig(profile="default", region="us-east-1"),
    )
    config.installer.source_code.repository_type = "codecommit"
    config.configuration.repository.type = "codeconnection"
    config.installer.options.use_existing_config_repo = True
    config.installer.options.enable_approval_stage = True

    assert is_installer_parameter_applicable(config, "RepositoryOwner") is False
    assert is_installer_parameter_applicable(config, "RepositoryName") is True
    assert is_installer_parameter_applicable(config, "ApprovalStageNotifyEmailList") is True
    assert is_installer_parameter_applicable(config, "UseExistingConfigRepo") is True
    assert is_installer_parameter_applicable(config, "ConfigCodeConnectionArn") is True
    assert is_installer_parameter_applicable(config, "ExistingConfigRepositoryOwner") is True
    assert is_installer_parameter_applicable(config, "ExistingConfigRepositoryName") is True
    assert is_installer_parameter_applicable(config, "ExistingConfigRepositoryBranchName") is True

