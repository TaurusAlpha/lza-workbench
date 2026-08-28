"""Tests for config_deploy workflow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lza_workbench.errors import LzaError
from lza_workbench.workflows.config_deploy import (
    ConfigDeployError,
    ConfigDeployResult,
    deploy_configuration_workflow,
)


def test_deploy_configuration_dry_run(configured_workspace: Path) -> None:
    result = deploy_configuration_workflow(
        target_dir=configured_workspace,
        dry_run=True,
    )
    assert isinstance(result, ConfigDeployResult)
    assert result.dry_run is True
    assert result.push_result is not None
    assert result.start_result is not None
    assert result.push_result.dry_run is True
    assert result.start_result.dry_run is True
    assert result.watch_result is None


def test_deploy_configuration_no_watch(configured_workspace: Path) -> None:
    mock_s3 = MagicMock()
    mock_s3.head_object.return_value = {"ETag": '"12345"', "VersionId": "v1"}
    mock_codepipeline = MagicMock()
    mock_codepipeline.start_pipeline_execution.return_value = {
        "pipelineExecutionId": "exec-deploy-123"
    }

    def get_client_side_effect(service_name: str) -> MagicMock:
        if service_name == "s3":
            return mock_s3
        if service_name == "codepipeline":
            return mock_codepipeline
        return MagicMock()

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client",
            side_effect=get_client_side_effect,
        ),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = deploy_configuration_workflow(
            target_dir=configured_workspace,
            dry_run=False,
            watch=False,
        )

    assert result.dry_run is False
    assert result.push_result is not None
    assert result.start_result is not None
    assert result.push_result.etag == "12345"
    assert result.start_result.execution_id == "exec-deploy-123"
    assert result.watch_result is None


def test_deploy_configuration_full(configured_workspace: Path) -> None:
    mock_s3 = MagicMock()
    mock_s3.head_object.return_value = {"ETag": '"12345"', "VersionId": "v1"}
    mock_codepipeline = MagicMock()
    mock_codepipeline.start_pipeline_execution.return_value = {
        "pipelineExecutionId": "exec-deploy-456"
    }
    mock_codepipeline.get_pipeline_execution.return_value = {
        "pipelineExecution": {
            "pipelineExecutionId": "exec-deploy-456",
            "status": "Succeeded",
        }
    }
    mock_codepipeline.get_pipeline_state.return_value = {
        "stageStates": [
            {
                "stageName": "Deploy",
                "latestExecution": {"status": "Succeeded"},
                "actionStates": [],
            }
        ]
    }

    def get_client_side_effect(service_name: str) -> MagicMock:
        if service_name == "s3":
            return mock_s3
        if service_name == "codepipeline":
            return mock_codepipeline
        return MagicMock()

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client",
            side_effect=get_client_side_effect,
        ),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = deploy_configuration_workflow(
            target_dir=configured_workspace,
            dry_run=False,
            watch=True,
            sleeper=lambda _: None,
        )

    assert result.dry_run is False
    assert result.push_result is not None
    assert result.start_result is not None
    assert result.push_result.etag == "12345"
    assert result.start_result.execution_id == "exec-deploy-456"
    assert result.watch_result is not None
    assert result.watch_result.status == "Succeeded"


def test_deploy_configuration_preserves_push_when_start_fails(configured_workspace: Path) -> None:
    push_result = MagicMock()
    aws_context = MagicMock()
    with (
        patch(
            "lza_workbench.workflows.config_deploy.resolve_aws_execution_context",
            return_value=aws_context,
        ),
        patch(
            "lza_workbench.workflows.config_deploy.push_configuration_workflow",
            return_value=push_result,
        ),
        patch(
            "lza_workbench.workflows.config_deploy.start_pipeline_workflow",
            side_effect=LzaError("start failed"),
        ),
    ):
        with pytest.raises(ConfigDeployError, match="push succeeded") as raised:
            deploy_configuration_workflow(target_dir=configured_workspace, watch=False)

    assert raised.value.result.push_result is push_result
    assert raised.value.result.start_result is None


def test_deploy_configuration_preserves_execution_when_watch_fails(
    configured_workspace: Path,
) -> None:
    push_result = MagicMock()
    start_result = MagicMock(execution_id="exec-123")
    aws_context = MagicMock()
    with (
        patch(
            "lza_workbench.workflows.config_deploy.resolve_aws_execution_context",
            return_value=aws_context,
        ),
        patch(
            "lza_workbench.workflows.config_deploy.push_configuration_workflow",
            return_value=push_result,
        ),
        patch(
            "lza_workbench.workflows.config_deploy.start_pipeline_workflow",
            return_value=start_result,
        ),
        patch(
            "lza_workbench.workflows.config_deploy.watch_pipeline_workflow",
            side_effect=LzaError("watch failed"),
        ),
    ):
        with pytest.raises(ConfigDeployError, match="exec-123") as raised:
            deploy_configuration_workflow(target_dir=configured_workspace)

    assert raised.value.result.push_result is push_result
    assert raised.value.result.start_result is start_result
