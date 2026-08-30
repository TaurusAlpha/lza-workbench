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
    assert "2. Failure" in result.output
    assert "Stage: Synth" in result.output
    assert "Action: SynthAction" in result.output
    assert "Error: Synth failed with error" in result.output


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
            "startTime": "2026-08-30T12:00:00+00:00",
            "lastUpdateTime": "2026-08-30T12:02:31+00:00",
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
                            "errorDetails": {
                                "message": (
                                    "Phase context status code: COMMAND_EXECUTION_ERROR "
                                    'Message: "Error while executing command: yarn run ts-node". '
                                    "Reason: exit status 1"
                                )
                            },
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
                    "2026-08-23 | error | toolkit | Deployment of Stack failed: "
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
    # Check concise duration
    assert "Duration: 2m 31s" in result.output
    # Check concise action table detail (not full raw buildspec dump)
    assert "CodeBuild BUILD phase failed" in result.output
    assert "exit status" in result.output
    assert "yarn run ts-node" not in result.output
    # Check clear failure section
    assert "2. Failure" in result.output
    assert "Stage: Prepare" in result.output
    assert "Action: PrepareAction" in result.output
    assert "Resource: AWSAccelerator-PrepareStack-376564958706-eu-west-1" in result.output
    assert "ValidationError: Stack cannot be deleted while" in result.output
    assert "TerminationProtection" in result.output
    assert "https://console.aws.amazon.com/codebuild/build-abc-123" in result.output


    # Presentation emoji ❌ should be stripped from domain error output
    assert "❌" not in result.output




def test_cli_pipeline_watch_concise_omits_pending_stages_on_failure(
    configured_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_codepipeline = MagicMock()
    mock_codepipeline.get_pipeline_execution.return_value = {
        "pipelineExecution": {
            "pipelineExecutionId": "exec-concise-fail",
            "status": "Failed",
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
            },
            {
                "stageName": "Prepare",
                "latestExecution": {"status": "Failed"},
                "actionStates": [
                    {
                        "actionName": "PrepareAction",
                        "latestExecution": {
                            "status": "Failed",
                            "errorDetails": {"message": "Prepare step failed"},
                        },
                    }
                ],
            },
            {
                "stageName": "Accounts",
                "actionStates": [
                    {"actionName": "AccountsAction"}
                ],
            },
            {
                "stageName": "Network",
                "actionStates": [
                    {"actionName": "NetworkAction"}
                ],
            },
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
        # Default concise mode
        result = cli_runner.invoke(app, ["pipeline", "watch", "-e", "exec-concise-fail"])
        assert result.exit_code == 1
        assert "Source" in result.output
        assert "Prepare" in result.output
        # Pending stages after failure should be omitted from table
        assert "Accounts" not in result.output
        assert "Network" not in result.output

        # Verbose mode should show pending stages
        result_verbose = cli_runner.invoke(
            app, ["pipeline", "watch", "-e", "exec-concise-fail", "--verbose"]
        )
        assert result_verbose.exit_code == 1

        assert "Source" in result_verbose.output
        assert "Prepare" in result_verbose.output
        assert "Accounts" in result_verbose.output
        assert "Network" in result_verbose.output


def test_cli_pipeline_watch_omits_duration_when_unknown(
    configured_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_codepipeline = MagicMock()
    mock_codepipeline.get_pipeline_execution.return_value = {
        "pipelineExecution": {
            "pipelineExecutionId": "exec-unknown-dur",
            "status": "Succeeded",
            # No startTime or lastUpdateTime
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
        result = cli_runner.invoke(app, ["pipeline", "watch", "-e", "exec-unknown-dur"])

    assert result.exit_code == 0
    assert "Pipeline Execution Summary" in result.output
    # When duration cannot be determined reliably, Duration line should be omitted
    assert "Duration:" not in result.output
    assert "Duration: 0 seconds" not in result.output



