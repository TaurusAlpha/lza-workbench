"""Tests for installer deploy workflow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lza_workbench.errors import LzaError
from lza_workbench.infrastructure.aws.cloudformation import (
    CfnDeploymentPlanResult,
    CfnStackStatusResult,
)
from lza_workbench.infrastructure.aws.session import AwsExecutionContext
from lza_workbench.installer.deploy import (
    InstallerDeploymentPreparation,
    InstallerDeployResult,
    apply_installer_deployment,
    deploy_installer_workflow,
    prepare_installer_deployment,
)
from lza_workbench.workspace.persistence import (
    load_workspace_config,
    load_workspace_state,
    write_workspace_state,
)


def test_deploy_installer_workflow_dry_run(configured_workspace: Path) -> None:
    with (
        patch("lza_workbench.infrastructure.aws.session.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.infrastructure.aws.session.AwsClientFactory.get_client") as mock_client,
        patch("lza_workbench.installer.deploy.inspect_installer_source") as mock_src,
        patch(
            "lza_workbench.installer.deploy.inspect_cloudformation_stack"
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


@patch("lza_workbench.installer.deploy.inspect_cloudformation_stack")
@patch("lza_workbench.installer.deploy.inspect_installer_source")
@patch("lza_workbench.installer.deploy.resolve_aws_execution_context")
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
    state.installer.template.digest = "outdated"
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


@patch("lza_workbench.installer.deploy.stream_cloudformation_stack_events")
@patch("lza_workbench.installer.deploy.deploy_cloudformation_stack")
@patch("lza_workbench.installer.deploy.upload_s3_file")
@patch("lza_workbench.installer.deploy.inspect_s3_bucket")
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
    from lza_workbench.infrastructure.aws.s3 import S3BucketObservation

    mock_inspect_bucket.return_value = S3BucketObservation(exists=True, accessible=True)
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
    assert state.installer.observation is not None
    assert state.installer.observation.stack_id == "stack-id"
    assert state.installer.observation.stack_status == "UPDATE_ROLLBACK_COMPLETE"
    assert state.installer.last_deployment is not None
    assert state.installer.last_deployment.stack_status == "UPDATE_ROLLBACK_COMPLETE"


def test_prepare_installer_deployment_validates_injected_aws_context_account(
    configured_workspace: Path,
) -> None:
    config = load_workspace_config(configured_workspace)
    config.aws.account_id = "123456789012"
    mismatched_context = AwsExecutionContext(
        region="us-east-1",
        factory=MagicMock(),
        identity={"account": "999999999999", "arn": "arn:aws:iam::999999999999:user/other"},
        error=None,
    )

    with pytest.raises(LzaError, match="999999999999"):
        prepare_installer_deployment(
            config=config,
            workspace_dir=configured_workspace,
            aws_context=mismatched_context,
        )


@patch("lza_workbench.installer.deploy.inspect_cloudformation_stack")
@patch("lza_workbench.installer.deploy.inspect_installer_source")
@patch("lza_workbench.installer.deploy.inspect_s3_bucket")
def test_prepare_installer_deployment_explicit_template_applies_anonymous_data(
    mock_inspect_bucket: MagicMock,
    mock_inspect_source: MagicMock,
    mock_inspect_cfn: MagicMock,
    configured_workspace: Path,
    tmp_path: Path,
) -> None:
    from lza_workbench.infrastructure.aws.s3 import S3BucketObservation

    source_template = tmp_path / "source-installer.template"
    source_content = """{
  "Mappings": {
    "SendAnonymizedData": {
      "SendAnonymizedData": {
        "Data": "Yes"
      }
    }
  },
  "Parameters": {
    "ManagementAccountEmail": {"Type": "String"},
    "LogArchiveAccountEmail": {"Type": "String"},
    "AuditAccountEmail": {"Type": "String"},
    "RepositorySource": {"Type": "String", "Default": "github"},
    "RepositoryBranchName": {"Type": "String", "Default": "release/v1.15.5"}
  }
}
"""
    source_template.write_text(source_content, encoding="utf-8")

    config = load_workspace_config(configured_workspace)
    config.installer.options.anonymous_data = False
    aws_context = AwsExecutionContext(
        region="us-east-1",
        factory=MagicMock(),
        identity={"account": "123456789012", "arn": "arn:aws:iam::123456789012:user/test"},
        error=None,
    )
    mock_inspect_bucket.return_value = S3BucketObservation(
        exists=True, accessible=True, versioning_enabled=True
    )
    mock_inspect_source.return_value = None
    mock_inspect_cfn.return_value = CfnDeploymentPlanResult(
        stack_name="AWSAccelerator-InstallerStack",
        operation="CREATE",
        stack_status=None,
        resolved_parameters={},
    )

    preparation = prepare_installer_deployment(
        config=config,
        template_path=source_template,
        aws_context=aws_context,
    )

    assert source_template.read_text(encoding="utf-8") == source_content
    assert preparation.template_path != source_template
    assert '"Data": "No"' in preparation.template_path.read_text(encoding="utf-8")


@patch("lza_workbench.installer.deploy.inspect_cloudformation_stack")
@patch("lza_workbench.installer.deploy.inspect_installer_source")
@patch("lza_workbench.installer.deploy.inspect_s3_bucket")
def test_installer_workflows_accept_target_and_installer_without_workspace_config(
    mock_inspect_bucket: MagicMock,
    mock_inspect_source: MagicMock,
    mock_inspect_cfn: MagicMock,
    configured_workspace: Path,
) -> None:
    from lza_workbench.infrastructure.aws.codepipeline import PipelineStateResult
    from lza_workbench.infrastructure.aws.s3 import S3BucketObservation
    from lza_workbench.infrastructure.aws.session import AwsClientFactory
    from lza_workbench.installer.plan import plan_installer_workflow
    from lza_workbench.installer.status import get_installer_status_workflow

    config = load_workspace_config(configured_workspace)
    env_target = config.environment_target.model_copy(
        update={"installer_stack_name": "Customer-Installer"}
    )
    installer = config.installer
    assert installer.stack_name == "AWSAccelerator-InstallerStack"
    template_path = (
        configured_workspace
        / config.installer.local_path
        / "AWSAccelerator-InstallerStack.template"
    )
    factory = AwsClientFactory(profile="agent-profile", region="us-east-1")
    factory.get_client = MagicMock(return_value=MagicMock())  # type: ignore[method-assign]
    aws_context = AwsExecutionContext(
        region="us-east-1",
        factory=factory,
        identity={"account": "123456789012", "arn": "arn:aws:iam::123456789012:user/test"},
        error=None,
    )
    mock_inspect_bucket.return_value = S3BucketObservation(
        exists=True, accessible=True, versioning_enabled=True
    )
    mock_inspect_source.return_value = None
    mock_inspect_cfn.return_value = CfnDeploymentPlanResult(
        stack_name="Customer-Installer",
        operation="CREATE",
        stack_status=None,
        resolved_parameters={"AcceleratorPrefix": "AWSAccelerator"},
    )

    with (
        patch(
            "lza_workbench.installer.status._query_live_installer_status",
            return_value=(
                CfnStackStatusResult(
                    stack_name="Customer-Installer",
                    exists=True,
                    stack_status="CREATE_COMPLETE",
                    deployed_parameters={"AcceleratorPrefix": "AWSAccelerator"},
                ),
                "v1.15.5",
                PipelineStateResult(
                    pipeline_name="AWSAccelerator-Installer",
                    exists=True,
                    status="Succeeded",
                ),
            ),
        ) as mock_query_live,
        patch(
            "lza_workbench.installer.plan.inspect_s3_bucket",
            return_value=mock_inspect_bucket.return_value,
        ),
        patch(
            "lza_workbench.installer.plan.inspect_cloudformation_stack",
            return_value=mock_inspect_cfn.return_value,
        ) as mock_plan_cfn,
        patch("lza_workbench.installer.plan.inspect_secret_exists", return_value=(True, None)),
    ):
        status_result = get_installer_status_workflow(
            environment_target=env_target,
            installer=installer,
            aws_context=aws_context,
        )
        plan_result = plan_installer_workflow(
            environment_target=env_target,
            installer=installer,
            template_path=template_path,
            aws_context=aws_context,
            dry_run=True,
        )

    preparation = prepare_installer_deployment(
        environment_target=env_target,
        installer=installer,
        template_path=template_path,
        aws_context=aws_context,
        dry_run=True,
    )

    assert status_result.config is None
    assert status_result.profile == "agent-profile"
    assert status_result.environment_target == env_target
    assert mock_query_live.call_args.kwargs["cfn_stack_name"] == "Customer-Installer"
    assert plan_result.config is None
    assert plan_result.profile == "agent-profile"
    assert plan_result.environment_target == env_target
    assert plan_result.installer == installer
    assert mock_plan_cfn.call_args.kwargs["stack_name"] == "Customer-Installer"
    assert preparation.config is None
    assert preparation.profile == "agent-profile"
    assert preparation.stack_name == "Customer-Installer"
    assert preparation.environment_target == env_target
    assert preparation.installer == installer


