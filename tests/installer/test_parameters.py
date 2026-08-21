"""Tests for installer CloudFormation parameter assembly and mapping."""

from __future__ import annotations

from lza_workbench.installer.parameters import (
    apply_installer_parameter,
    build_installer_cfn_parameters,
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
