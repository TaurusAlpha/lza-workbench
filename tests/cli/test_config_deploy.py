"""Tests for lza config deploy CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from lza_workbench.cli import app
from lza_workbench.workspace.state import load_workspace_state


def test_cli_config_deploy_dry_run(
    configured_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(configured_workspace)
    result = cli_runner.invoke(app, ["config", "deploy", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert "Step 1: Configuration Push" in result.output
    assert "Step 2: Pipeline Execution" in result.output


def test_cli_config_deploy_no_watch_success(
    configured_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_s3 = MagicMock()
    mock_s3.head_object.return_value = {"ETag": '"12345"', "VersionId": "v1"}
    mock_codepipeline = MagicMock()
    mock_codepipeline.start_pipeline_execution.return_value = {
        "pipelineExecutionId": "exec-cli-123"
    }

    def get_client_side_effect(service_name: str) -> MagicMock:
        if service_name == "s3":
            return mock_s3
        if service_name == "codepipeline":
            return mock_codepipeline
        return MagicMock()

    monkeypatch.chdir(configured_workspace)
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client",
            side_effect=get_client_side_effect,
        ),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = cli_runner.invoke(app, ["config", "deploy", "--no-watch"])

    assert result.exit_code == 0
    assert "Packaged and uploaded LZA configuration" in result.output
    assert "Started pipeline execution for 'AWSAccelerator-Pipeline'" in result.output
    assert "exec-cli-123" in result.output

    state = load_workspace_state(configured_workspace)
    assert state.config_pipeline_execution_id == "exec-cli-123"


def test_cli_config_deploy_full_success(
    configured_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_s3 = MagicMock()
    mock_s3.head_object.return_value = {"ETag": '"12345"', "VersionId": "v1"}
    mock_codepipeline = MagicMock()
    mock_codepipeline.start_pipeline_execution.return_value = {
        "pipelineExecutionId": "exec-cli-456"
    }
    mock_codepipeline.get_pipeline_execution.return_value = {
        "pipelineExecution": {
            "pipelineExecutionId": "exec-cli-456",
            "status": "Succeeded",
        }
    }
    mock_codepipeline.get_pipeline_state.return_value = {
        "stageStates": [
            {
                "stageName": "Source",
                "latestExecution": {"status": "Succeeded"},
                "actionStates": [
                    {
                        "actionName": "SourceAction",
                        "latestExecution": {"status": "Succeeded"},
                    }
                ],
            },
            {
                "stageName": "Deploy",
                "latestExecution": {"status": "Succeeded"},
                "actionStates": [
                    {
                        "actionName": "DeployAction",
                        "latestExecution": {"status": "Succeeded"},
                    }
                ],
            },
        ]
    }

    def get_client_side_effect(service_name: str) -> MagicMock:
        if service_name == "s3":
            return mock_s3
        if service_name == "codepipeline":
            return mock_codepipeline
        return MagicMock()

    monkeypatch.chdir(configured_workspace)
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client",
            side_effect=get_client_side_effect,
        ),
        patch("time.sleep"),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = cli_runner.invoke(app, ["config", "deploy"])

    assert result.exit_code == 0
    assert "3. Pipeline Monitoring" in result.output
    assert "Stage & Action Breakdown" in result.output
    assert "completed successfully" in result.output


def test_cli_config_deploy_pipeline_failed(
    configured_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_s3 = MagicMock()
    mock_s3.head_object.return_value = {"ETag": '"12345"', "VersionId": "v1"}
    mock_codepipeline = MagicMock()
    mock_codepipeline.start_pipeline_execution.return_value = {
        "pipelineExecutionId": "exec-cli-fail"
    }
    mock_codepipeline.get_pipeline_execution.return_value = {
        "pipelineExecution": {
            "pipelineExecutionId": "exec-cli-fail",
            "status": "Failed",
        }
    }
    mock_codepipeline.get_pipeline_state.return_value = {
        "stageStates": [
            {
                "stageName": "Build",
                "latestExecution": {"status": "Failed"},
                "actionStates": [
                    {
                        "actionName": "CodeBuildSynthesize",
                        "latestExecution": {
                            "status": "Failed",
                            "errorDetails": {"message": "CDK Synth error"},
                        },
                    }
                ],
            }
        ]
    }

    def get_client_side_effect(service_name: str) -> MagicMock:
        if service_name == "s3":
            return mock_s3
        if service_name == "codepipeline":
            return mock_codepipeline
        return MagicMock()

    monkeypatch.chdir(configured_workspace)
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client",
            side_effect=get_client_side_effect,
        ),
        patch("time.sleep"),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = cli_runner.invoke(app, ["config", "deploy"])

    assert result.exit_code == 1
    assert "Pipeline execution 'exec-cli-fail' ended with status 'Failed'." in str(
        result.exception
    ) or "Pipeline execution 'exec-cli-fail' ended with status 'Failed'." in (result.output or "")
    assert "CDK Synth error" in result.output


def test_cli_config_deploy_verbose(
    configured_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_s3 = MagicMock()
    mock_s3.head_object.return_value = {"ETag": '"12345"', "VersionId": "v1"}
    mock_codepipeline = MagicMock()
    mock_codepipeline.start_pipeline_execution.return_value = {
        "pipelineExecutionId": "exec-cli-verb"
    }
    mock_codepipeline.get_pipeline_execution.return_value = {
        "pipelineExecution": {
            "pipelineExecutionId": "exec-cli-verb",
            "status": "Succeeded",
        }
    }
    mock_codepipeline.get_pipeline_state.return_value = {
        "stageStates": [
            {
                "stageName": "Source",
                "latestExecution": {"status": "Succeeded"},
                "actionStates": [
                    {"actionName": "SourceAction", "latestExecution": {"status": "Succeeded"}}
                ],
            }
        ]
    }

    def get_client_side_effect(service_name: str) -> MagicMock:
        if service_name == "s3":
            return mock_s3
        if service_name == "codepipeline":
            return mock_codepipeline
        return MagicMock()

    monkeypatch.chdir(configured_workspace)
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client",
            side_effect=get_client_side_effect,
        ),
        patch("time.sleep"),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = cli_runner.invoke(app, ["config", "deploy", "--verbose"])

    assert result.exit_code == 0
    assert "3. Pipeline Monitoring" in result.output
    assert "completed successfully" in result.output
