"""Tests for installer deploy workflow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lza_workbench.aws.cloudformation import CfnDeploymentPlanResult, CfnStackStatusResult
from lza_workbench.aws.context import AwsExecutionContext
from lza_workbench.errors import LzaError
from lza_workbench.workflows.installer_deploy import (
    InstallerDeploymentPreparation,
    InstallerDeployResult,
    apply_installer_deployment,
    deploy_installer_workflow,
    prepare_installer_deployment,
)
from lza_workbench.workspace.config import load_workspace_config
from lza_workbench.workspace.state import load_workspace_state, write_workspace_state


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


@patch("lza_workbench.workflows.installer_deploy.inspect_cloudformation_stack")
@patch("lza_workbench.workflows.installer_deploy.inspect_installer_source")
@patch("lza_workbench.workflows.installer_deploy.resolve_aws_execution_context")
def test_prepare_installer_deployment_updates_for_changed_template(
    mock_resolve_context: MagicMock,
    mock_inspect_source: MagicMock,
    mock_inspect_cfn: MagicMock,
    configured_workspace: Path,
) -> None:
    template_path = configured_workspace / "aws-accelerator-installer" / (
        "AWSAccelerator-InstallerStack.template"
    )
    state = load_workspace_state(configured_workspace)
    state.installer_template_digest = "outdated"
    write_workspace_state(configured_workspace, state)

    mock_factory = MagicMock()
    mock_resolve_context.return_value = AwsExecutionContext(
        region="us-east-1",
        factory=mock_factory,
        identity={"account": "123456789012", "arn": "arn:aws:iam::123:user/test"},
        error=None,
    )
    mock_inspect_source.return_value = None
    mock_inspect_cfn.return_value = CfnDeploymentPlanResult(
        stack_name="AWSAccelerator-InstallerStack",
        operation="NO_CHANGE",
        stack_status="UPDATE_COMPLETE",
        resolved_parameters={},
    )

    preparation = prepare_installer_deployment(target_dir=configured_workspace)

    assert template_path.exists()
    assert preparation.operation == "UPDATE"


@patch("lza_workbench.workflows.installer_deploy.stream_cloudformation_stack_events")
@patch("lza_workbench.workflows.installer_deploy.deploy_cloudformation_stack")
@patch("lza_workbench.workflows.installer_deploy.upload_s3_file")
@patch("lza_workbench.workflows.installer_deploy.inspect_s3_bucket")
def test_apply_installer_deployment_records_terminal_failure(
    mock_inspect_bucket: MagicMock,
    mock_upload: MagicMock,
    mock_deploy: MagicMock,
    mock_stream: MagicMock,
    configured_workspace: Path,
) -> None:
    config = load_workspace_config(configured_workspace)
    template_path = configured_workspace / "aws-accelerator-installer" / (
        "AWSAccelerator-InstallerStack.template"
    )
    factory = MagicMock()
    preparation = InstallerDeploymentPreparation(
        workspace_dir=configured_workspace,
        config=config,
        aws_context=AwsExecutionContext(
            region="us-east-1",
            factory=factory,
            identity={"account": "123456789012", "arn": "arn:aws:iam::123:user/test"},
            error=None,
        ),
        template_path=template_path,
        template_digest="digest",
        resolved_parameters={},
        stack_name="AWSAccelerator-InstallerStack",
        operation="UPDATE",
        cfn_plan=CfnDeploymentPlanResult(
            stack_name="AWSAccelerator-InstallerStack",
            operation="UPDATE",
            stack_status="UPDATE_COMPLETE",
            resolved_parameters={},
        ),
        profile="test",
        account_id="123456789012",
    )
    mock_inspect_bucket.return_value = {"exists": True}
    mock_deploy.return_value = "stack-id"
    mock_stream.return_value = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack",
        exists=True,
        stack_id="stack-id",
        stack_status="UPDATE_ROLLBACK_COMPLETE",
    )

    with pytest.raises(LzaError, match="UPDATE_ROLLBACK_COMPLETE"):
        apply_installer_deployment(preparation=preparation)

    state = load_workspace_state(configured_workspace)
    assert state.installer_stack_id == "stack-id"
    assert state.installer_stack_status == "UPDATE_ROLLBACK_COMPLETE"
