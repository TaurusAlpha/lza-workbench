"""Tests for status workflows and status synchronization."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lza_workbench.aws.cloudformation import CfnStackStatusResult
from lza_workbench.errors import LzaError
from lza_workbench.workflows.status_config import (
    ConfigurationStatusResult,
    get_config_status_workflow,
)
from lza_workbench.workflows.status_installer import (
    InstallerStatusResult,
    get_installer_status_workflow,
    prepare_installer_status,
    sync_installer_config,
    sync_installer_state,
)
from lza_workbench.workflows.status_pipeline import (
    PipelineStatusResult,
    get_pipeline_status_workflow,
)
from lza_workbench.workflows.status_root import (
    RootStatusResult,
    get_root_status_workflow,
)
from lza_workbench.workspace.config import load_workspace_config
from lza_workbench.workspace.schema import (
    AwsConfig,
    CustomerConfig,
    WorkspaceConfig,
    WorkspaceState,
)
from lza_workbench.workspace.state import load_workspace_state


def test_get_root_status_workflow(configured_workspace: Path) -> None:
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        mock_client.return_value = MagicMock()
        result = get_root_status_workflow(target_dir=configured_workspace)
        assert isinstance(result, RootStatusResult)
        assert result.customer_name == "Acme Corp"
        assert result.profile == "acme-root"
        assert result.region == "eu-west-1"


def test_get_config_status_workflow(configured_workspace: Path) -> None:
    result = get_config_status_workflow(target_dir=configured_workspace)
    assert isinstance(result, ConfigurationStatusResult)
    assert result.customer_name == "Acme Corp"
    assert result.config_dir_exists is True
    assert result.repository_type == "s3"


def test_get_pipeline_status_workflow(configured_workspace: Path) -> None:
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        mock_client.return_value = MagicMock()
        result = get_pipeline_status_workflow(target_dir=configured_workspace)
        assert isinstance(result, PipelineStatusResult)
        assert result.installer_pipeline_name == "AWSAccelerator-Installer"
        assert result.config_pipeline_name == "AWSAccelerator-Pipeline"


def test_get_installer_status_workflow(configured_workspace: Path) -> None:
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
        patch(
            "lza_workbench.workflows.status_installer.get_cloudformation_stack_status"
        ) as mock_st,
        patch("lza_workbench.workflows.status_installer.get_pipeline_state") as mock_pipe,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        mock_client.return_value = MagicMock()
        mock_st.return_value = CfnStackStatusResult(
            stack_name="AWSAccelerator-InstallerStack",
            exists=True,
            stack_status="CREATE_COMPLETE",
            stack_id="arn:aws:cloudformation:stack/123",
            deployed_parameters={"RepositoryBranchName": "release/v1.16.0"},
            outputs={"OutputKey": "OutputVal"},
        )
        mock_pipe.return_value = MagicMock(
            pipeline_name="AWSAccelerator-Installer", exists=True, status="Succeeded"
        )
        result = get_installer_status_workflow(target_dir=configured_workspace)
        assert isinstance(result, InstallerStatusResult)
        assert result.cfn_status.exists is True
        assert result.deployed_version == "v1.16.0"
        assert result.pipeline_state is not None
        assert result.pipeline_state.status == "Succeeded"


def test_sync_installer_state_raises_when_not_exists(tmp_path: Path) -> None:
    state = WorkspaceState()
    cfn_status = CfnStackStatusResult(stack_name="AWSAccelerator-InstallerStack", exists=False)
    with pytest.raises(LzaError, match="Cannot synchronize state"):
        sync_installer_state(
            workspace_dir=tmp_path,
            state=state,
            cfn_status=cfn_status,
            deployed_version="v1.15.5",
        )


def test_sync_installer_state_success(tmp_path: Path) -> None:
    state = WorkspaceState()
    cfn_status = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack",
        exists=True,
        stack_id="arn:aws:cloudformation:us-east-1:123:stack/test/123",
        stack_status="CREATE_COMPLETE",
    )
    new_state = sync_installer_state(
        workspace_dir=tmp_path,
        state=state,
        cfn_status=cfn_status,
        deployed_version="v1.15.5",
    )
    assert new_state.installer_stack_id == cfn_status.stack_id
    assert new_state.installer_stack_status == "CREATE_COMPLETE"
    assert new_state.installer_template_version == "v1.15.5"

    loaded_state = load_workspace_state(tmp_path)
    assert loaded_state.installer_stack_id == cfn_status.stack_id


def test_sync_installer_config_success(tmp_path: Path) -> None:
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
    )
    cfn_status = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack",
        exists=True,
        deployed_parameters={
            "RepositorySource": "codecommit",
            "RepositoryOwner": "aws",
            "RepositoryName": "aws-accelerator",
            "RepositoryBranchName": "release/v1.15.5",
            "ManagementAccountEmail": "mgmt@example.com",
            "EnableApprovalStage": "Yes",
        },
    )
    new_config = sync_installer_config(
        workspace_dir=tmp_path,
        config=config,
        cfn_status=cfn_status,
    )
    assert new_config.installer.source_code.repository_type == "codecommit"
    assert new_config.installer.options.management_account_email == "mgmt@example.com"
    assert new_config.installer.options.enable_approval_stage is True

    loaded_config = load_workspace_config(tmp_path)
    assert loaded_config.installer.options.management_account_email == "mgmt@example.com"


def test_sync_installer_config_accepts_codeconnection_repository(tmp_path: Path) -> None:
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
    )
    cfn_status = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack",
        exists=True,
        deployed_parameters={"ConfigurationRepositoryLocation": "codeconnection"},
    )

    new_config = sync_installer_config(
        workspace_dir=tmp_path,
        config=config,
        cfn_status=cfn_status,
    )

    assert new_config.configuration.repository.type == "codeconnection"


def test_prepare_installer_status_separates_comparisons_from_rendering(tmp_path: Path) -> None:
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
    )
    state = WorkspaceState(
        installer_stack_status="CREATE_COMPLETE",
        installer_template_version="v1.15.5",
    )
    cfn_status = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack",
        exists=True,
        stack_status="CREATE_COMPLETE",
        deployed_parameters={"RepositoryBranchName": "release/v1.15.5"},
    )

    result = prepare_installer_status(
        workspace_dir=tmp_path,
        config=config,
        state=state,
        profile="test-profile",
        region="us-east-1",
        aws_identity=None,
        aws_error="No credentials",
        cfn_status=cfn_status,
    )

    assert result.deployed_version == "v1.15.5"
    assert result.state_alignment is not None
    assert result.state_alignment.in_sync is True
