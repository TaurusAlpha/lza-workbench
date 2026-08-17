"""Tests for status workflows."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lza_workbench.aws.cloudformation import CfnStackStatusResult
from lza_workbench.commands.workspace_init import run_init
from lza_workbench.workflows.status_config import (
    ConfigurationStatusResult,
    get_config_status_workflow,
)
from lza_workbench.workflows.status_installer import (
    InstallerStatusResult,
    get_installer_status_workflow,
)
from lza_workbench.workflows.status_pipeline import (
    PipelineStatusResult,
    get_pipeline_status_workflow,
)
from lza_workbench.workflows.status_root import (
    RootStatusResult,
    get_root_status_workflow,
)


@pytest.fixture
def status_workspace(tmp_path: Path) -> Path:
    ws_dir = tmp_path / "status-corp"
    run_init(
        customer_name="Status Corp",
        workspace_dir=ws_dir,
        aws_profile="status-profile",
        aws_region="us-east-1",
        skip_aws_check=True,
        dry_run=False,
        force=False,
        interactive=False,
    )
    return ws_dir


def test_get_root_status_workflow(status_workspace: Path) -> None:
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        mock_client.return_value = MagicMock()
        result = get_root_status_workflow(target_dir=status_workspace)
        assert isinstance(result, RootStatusResult)
        assert result.customer_name == "Status Corp"
        assert result.profile == "status-profile"
        assert result.region == "us-east-1"


def test_get_config_status_workflow(status_workspace: Path) -> None:
    result = get_config_status_workflow(target_dir=status_workspace)
    assert isinstance(result, ConfigurationStatusResult)
    assert result.customer_name == "Status Corp"
    assert result.config_dir_exists is True
    assert result.repository_type == "codecommit"


def test_get_pipeline_status_workflow(status_workspace: Path) -> None:
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        mock_client.return_value = MagicMock()
        result = get_pipeline_status_workflow(target_dir=status_workspace)
        assert isinstance(result, PipelineStatusResult)
        assert result.installer_pipeline_name == "AWSAccelerator-Installer"
        assert result.config_pipeline_name == "AWSAccelerator-Pipeline"


def test_get_installer_status_workflow(status_workspace: Path) -> None:
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
        patch(
            "lza_workbench.workflows.status_installer.get_cloudformation_stack_status"
        ) as mock_st,
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
        result = get_installer_status_workflow(target_dir=status_workspace)
        assert isinstance(result, InstallerStatusResult)
        assert result.cfn_status.exists is True
        assert result.deployed_version == "v1.16.0"
