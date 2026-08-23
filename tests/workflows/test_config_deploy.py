"""Tests for config_deploy workflow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from lza_workbench.workflows.config_deploy import (
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
    assert result.push_result.etag == "12345"
    assert result.start_result.execution_id == "exec-deploy-456"
    assert result.watch_result is not None
    assert result.watch_result.status == "Succeeded"
