"""Tests for lza pipeline start and lza pipeline watch CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from lza_workbench.cli import app
from lza_workbench.workspace.state import load_workspace_state


def test_cli_pipeline_start_dry_run(
    configured_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(configured_workspace)
    result = cli_runner.invoke(app, ["pipeline", "start", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert "Start pipeline execution" in result.output
    assert "AWSAccelerator-Pipeline" in result.output


def test_cli_pipeline_start_success(
    configured_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_codepipeline = MagicMock()
    mock_codepipeline.start_pipeline_execution.return_value = {
        "pipelineExecutionId": "exec-start-789"
    }

    monkeypatch.chdir(configured_workspace)
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client",
            return_value=mock_codepipeline,
        ),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = cli_runner.invoke(app, ["pipeline", "start"])

    assert result.exit_code == 0
    assert "Started pipeline execution for 'AWSAccelerator-Pipeline'" in result.output
    assert "exec-start-789" in result.output

    state = load_workspace_state(configured_workspace)
    assert state.config_pipeline_execution_id == "exec-start-789"


def test_cli_pipeline_watch_success(
    configured_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_codepipeline = MagicMock()
    mock_codepipeline.get_pipeline_execution.return_value = {
        "pipelineExecution": {
            "pipelineExecutionId": "exec-watch-555",
            "status": "Succeeded",
        }
    }
    mock_codepipeline.get_pipeline_state.return_value = {
        "stageStates": [
            {
                "stageName": "Deploy",
                "latestExecution": {"status": "Succeeded"},
                "actionStates": [
                    {
                        "actionName": "DeployAction",
                        "latestExecution": {"status": "Succeeded"},
                    }
                ],
            }
        ]
    }

    monkeypatch.chdir(configured_workspace)
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client",
            return_value=mock_codepipeline,
        ),
        patch("time.sleep"),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = cli_runner.invoke(app, ["pipeline", "watch", "-e", "exec-watch-555"])

    assert result.exit_code == 0
    assert "Pipeline Execution Summary" in result.output
    assert "completed successfully" in result.output


def test_cli_pipeline_watch_failure(
    configured_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_codepipeline = MagicMock()
    mock_codepipeline.get_pipeline_execution.return_value = {
        "pipelineExecution": {
            "pipelineExecutionId": "exec-watch-fail",
            "status": "Failed",
        }
    }
    mock_codepipeline.get_pipeline_state.return_value = {
        "stageStates": [
            {
                "stageName": "Synth",
                "latestExecution": {"status": "Failed"},
                "actionStates": [
                    {
                        "actionName": "SynthAction",
                        "latestExecution": {
                            "status": "Failed",
                            "errorDetails": {"message": "Synth failed with error"},
                        },
                    }
                ],
            }
        ]
    }

    monkeypatch.chdir(configured_workspace)
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client",
            return_value=mock_codepipeline,
        ),
        patch("time.sleep"),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = cli_runner.invoke(app, ["pipeline", "watch", "-e", "exec-watch-fail"])

    assert result.exit_code == 1
    assert "execution failed" in result.output
    assert "Synth failed with error" in result.output


def test_cli_pipeline_watch_with_diagnostics(
    configured_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_codepipeline = MagicMock()
    mock_codepipeline.get_pipeline_execution.return_value = {
        "pipelineExecution": {
            "pipelineExecutionId": "exec-cli-diag",
            "status": "Failed",
        }
    }
    mock_codepipeline.get_pipeline_state.return_value = {
        "stageStates": [
            {
                "stageName": "Prepare",
                "latestExecution": {"status": "Failed"},
                "actionStates": [
                    {
                        "actionName": "PrepareAction",
                        "latestExecution": {
                            "status": "Failed",
                            "errorDetails": {"message": "Build command failed"},
                            "externalExecutionId": "build-abc-123",
                            "externalExecutionUrl": "https://console.aws.amazon.com/codebuild/build-abc-123",
                        },
                    }
                ],
            }
        ]
    }

    mock_codebuild = MagicMock()
    mock_codebuild.batch_get_builds.return_value = {
        "builds": [
            {
                "id": "build-abc-123",
                "logs": {
                    "groupName": "/aws/codebuild/lza",
                    "streamName": "stream-1",
                },
            }
        ]
    }
    mock_logs = MagicMock()
    mock_logs.get_log_events.return_value = {
        "events": [
            {
                "message": (
                    "❌  AWSAccelerator-PrepareStack-376564958706-eu-west-1 failed: "
                    "ValidationError: Stack cannot be deleted while "
                    "TerminationProtection is enabled"
                )
            }
        ]
    }

    def get_client(service: str) -> MagicMock:
        if service == "codepipeline":
            return mock_codepipeline
        if service == "codebuild":
            return mock_codebuild
        if service == "logs":
            return mock_logs
        return MagicMock()

    monkeypatch.chdir(configured_workspace)
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client",
            side_effect=get_client,
        ),
        patch("time.sleep"),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = cli_runner.invoke(app, ["pipeline", "watch", "-e", "exec-cli-diag"])

    assert result.exit_code == 1
    assert "Action Failures & Diagnostics" in result.output
    assert "PrepareAction" in result.output
    assert "TerminationProtection is enabled" in result.output
    assert "https://console.aws.amazon.com/codebuild/build-abc-123" in result.output

