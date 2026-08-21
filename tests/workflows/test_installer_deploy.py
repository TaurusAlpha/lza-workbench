"""Tests for installer deploy workflow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from lza_workbench.aws.cloudformation import CfnDeploymentPlanResult
from lza_workbench.workflows.installer_deploy import (
    InstallerDeployResult,
    deploy_installer_workflow,
)


def test_deploy_installer_workflow_dry_run(configured_workspace: Path) -> None:
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
        patch("lza_workbench.installer.deployment.inspect_installer_source") as mock_src,
        patch(
            "lza_workbench.workflows.installer_deploy.inspect_cloudformation_stack"
        ) as mock_inspect,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        mock_client.return_value = MagicMock()
        mock_src.return_value = None
        mock_inspect.return_value = CfnDeploymentPlanResult(
            stack_name="AWSAccelerator-InstallerStack",
            operation="CREATE",
            stack_status=None,
            resolved_parameters={},
            parameter_diffs={},
        )

        result = deploy_installer_workflow(
            target_dir=configured_workspace,
            dry_run=True,
        )
        assert isinstance(result, InstallerDeployResult)
        assert result.dry_run is True
        assert result.skipped is False
        assert result.operation == "CREATE"
        assert result.stack_name == "AWSAccelerator-InstallerStack"
