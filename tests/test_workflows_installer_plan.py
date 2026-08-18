"""Tests for installer plan workflow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lza_workbench.installer.planning import InstallerPlanResult
from lza_workbench.installer.versions import PACKAGED_INSTALLER_VERSION
from lza_workbench.workflows.installer_plan import plan_installer_workflow
from lza_workbench.workflows.workspace_init import init_workspace_workflow


@pytest.fixture
def sample_workspace(tmp_path: Path) -> Path:
    ws_dir = tmp_path / "sample"
    init_workspace_workflow(
        customer_name="Sample Corp",
        workspace_dir=ws_dir,
        aws_profile="dev-profile",
        aws_region="us-east-1",
        lza_version=PACKAGED_INSTALLER_VERSION,
        skip_aws_check=True,
        dry_run=False,
        force=False,
    )
    from lza_workbench.workspace.config import load_workspace_config, write_workspace_config

    config = load_workspace_config(ws_dir)
    config.installer.options.management_account_email = "mgmt@example.com"
    config.installer.options.log_archive_account_email = "log@example.com"
    config.installer.options.audit_account_email = "audit@example.com"
    write_workspace_config(ws_dir, config)
    return ws_dir


def test_plan_installer_workflow_returns_structured_result(sample_workspace: Path) -> None:
    with patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val:
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        with patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client:
            mock_client.return_value = MagicMock()
            result = plan_installer_workflow(
                target_dir=sample_workspace,
                dry_run=True,
                no_save=True,
            )
            assert isinstance(result, InstallerPlanResult)
            assert result.workspace_dir == sample_workspace
            assert result.dry_run is True
            assert result.region == "us-east-1"
            assert result.aws_identity is not None
            assert result.aws_identity["account"] == "123456789012"
