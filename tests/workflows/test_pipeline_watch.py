"""Tests for pipeline_watch workflow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lza_workbench.aws.codepipeline import PipelineExecutionResult
from lza_workbench.errors import LzaError
from lza_workbench.workflows.pipeline_watch import (
    PipelineWatchResult,
    PipelineWatchUpdate,
    watch_pipeline_workflow,
)
from lza_workbench.workspace.state import load_workspace_state, write_workspace_state


def test_watch_pipeline_success(configured_workspace: Path) -> None:
    state = load_workspace_state(configured_workspace)
    state.config_pipeline_execution_id = "exec-test-123"
    state.config_pipeline_name = "AWSAccelerator-Pipeline"
    write_workspace_state(configured_workspace, state)

    mock_client = MagicMock()
    mock_client.get_pipeline_execution.return_value = {
        "pipelineExecution": {
            "pipelineExecutionId": "exec-test-123",
            "status": "Succeeded",
        }
    }
    mock_client.get_pipeline_state.return_value = {
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
            }
        ]
    }

    updates: list[PipelineWatchUpdate] = []

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client", return_value=mock_client
        ),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = watch_pipeline_workflow(
            target_dir=configured_workspace,
            sleeper=lambda _: None,
            on_update=updates.append,
        )

    assert isinstance(result, PipelineWatchResult)
    assert result.status == "Succeeded"
    assert result.execution_id == "exec-test-123"
    assert len(result.stages) == 1
    assert result.stages[0].stage_name == "Source"
    assert len(updates) == 1


def test_watch_pipeline_ignores_execution_for_a_different_recorded_pipeline(
    configured_workspace: Path,
) -> None:
    state = load_workspace_state(configured_workspace)
    state.config_pipeline_execution_id = "exec-other-pipeline"
    state.config_pipeline_name = "Other-Pipeline"
    write_workspace_state(configured_workspace, state)

    mock_client = MagicMock()
    mock_client.get_pipeline_execution.return_value = {
        "pipelineExecution": {
            "pipelineExecutionId": "exec-current-pipeline",
            "status": "Succeeded",
        }
    }
    mock_client.get_pipeline_state.return_value = {"stageStates": []}

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client", return_value=mock_client
        ),
        patch(
            "lza_workbench.workflows.pipeline_watch.get_latest_pipeline_execution_id",
            return_value="exec-current-pipeline",
        ) as mock_latest,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = watch_pipeline_workflow(target_dir=configured_workspace)

    assert result.execution_id == "exec-current-pipeline"
    mock_latest.assert_called_once_with(
        client=mock_client,
        pipeline_name="AWSAccelerator-Pipeline",
    )


def test_watch_pipeline_failed_action(configured_workspace: Path) -> None:
    mock_client = MagicMock()
    mock_client.get_pipeline_execution.return_value = {
        "pipelineExecution": {
            "pipelineExecutionId": "exec-fail-999",
            "status": "Failed",
        }
    }
    mock_client.get_pipeline_state.return_value = {
        "stageStates": [
            {
                "stageName": "Build",
                "latestExecution": {"status": "Failed"},
                "actionStates": [
                    {
                        "actionName": "CodeBuildSynthesize",
                        "latestExecution": {
                            "status": "Failed",
                            "errorDetails": {"message": "Build command exited with code 1"},
                        },
                    }
                ],
            }
        ]
    }

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client", return_value=mock_client
        ),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = watch_pipeline_workflow(
            target_dir=configured_workspace,
            execution_id="exec-fail-999",
            sleeper=lambda _: None,
        )

    assert result.status == "Failed"
    assert len(result.failed_actions) == 1
    assert result.failed_actions[0].action_name == "CodeBuildSynthesize"
    assert "Build command exited with code 1" in (result.error_message or "")


def test_watch_pipeline_failed_action_with_codebuild_diagnostics(
    configured_workspace: Path,
) -> None:
    mock_codepipeline = MagicMock()
    mock_codepipeline.get_pipeline_execution.return_value = {
        "pipelineExecution": {
            "pipelineExecutionId": "exec-diag-999",
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
                        "actionName": "Prepare",
                        "latestExecution": {
                            "status": "Failed",
                            "errorDetails": {"message": "Command did not exit successfully"},
                            "externalExecutionId": "AWSAccelerator-ToolkitProject:build-id-123",
                            "externalExecutionUrl": "https://console.aws.amazon.com/codebuild/...",
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
                "id": "AWSAccelerator-ToolkitProject:build-id-123",
                "logs": {
                    "groupName": "AWSAccelerator-Module-Verbose-Logs",
                    "streamName": "prepare/build-123",
                },
            }
        ]
    }
    mock_logs = MagicMock()
    mock_logs.get_log_events.return_value = {
        "events": [
            {
                "message": (
                    "2026-08-23 16:47:44.027 | error | toolkit | Deployment of Stack failed: "
                    "❌  AWSAccelerator-PrepareStack failed: ValidationError: Stack cannot "
                    "be deleted while TerminationProtection is enabled"
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

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client",
            side_effect=get_client,
        ),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = watch_pipeline_workflow(
            target_dir=configured_workspace,
            execution_id="exec-diag-999",
            sleeper=lambda _: None,
        )

    assert result.status == "Failed"
    assert len(result.failed_actions) == 1
    assert result.failed_actions[0].action_name == "Prepare"
    assert result.failed_actions[0].failed_resource == "AWSAccelerator-PrepareStack"
    assert len(result.failed_actions[0].diagnostic_details) == 1
    assert "TerminationProtection is enabled" in result.failed_actions[0].diagnostic_details[0]
    assert "❌" not in result.failed_actions[0].diagnostic_details[0]
    assert "TerminationProtection is enabled" in (result.error_message or "")



def test_watch_pipeline_no_execution_id(configured_workspace: Path) -> None:
    mock_client = MagicMock()
    mock_client.list_pipeline_executions.return_value = {"pipelineExecutionSummaries": []}
    mock_client.get_pipeline_state.return_value = {"stageStates": []}

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client", return_value=mock_client
        ),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        with pytest.raises(LzaError, match="No execution found to watch"):
            watch_pipeline_workflow(
                target_dir=configured_workspace,
                sleeper=lambda _: None,
            )


def test_watch_pipeline_stops_when_execution_is_not_found(configured_workspace: Path) -> None:
    mock_client = MagicMock()
    missing_execution = PipelineExecutionResult(
        pipeline_name="AWSAccelerator-Pipeline",
        execution_id="missing-execution",
        status="NOT_FOUND",
        error="Execution does not exist",
    )

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client", return_value=mock_client
        ),
        patch(
            "lza_workbench.workflows.pipeline_watch.get_pipeline_execution",
            return_value=missing_execution,
        ),
        patch("lza_workbench.workflows.pipeline_watch.get_pipeline_state") as mock_get_state,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        with pytest.raises(LzaError, match="was not found"):
            watch_pipeline_workflow(
                target_dir=configured_workspace,
                execution_id="missing-execution",
            )

    mock_get_state.assert_not_called()


def test_watch_pipeline_rejects_non_positive_poll_interval(configured_workspace: Path) -> None:
    with pytest.raises(LzaError, match="greater than zero"):
        watch_pipeline_workflow(
            target_dir=configured_workspace,
            execution_id="exec-test-123",
            poll_interval_seconds=0,
        )


def test_watch_pipeline_timeout(configured_workspace: Path) -> None:
    mock_client = MagicMock()
    mock_client.get_pipeline_execution.return_value = {
        "pipelineExecution": {
            "pipelineExecutionId": "exec-running-111",
            "status": "InProgress",
        }
    }
    mock_client.get_pipeline_state.return_value = {
        "stageStates": [
            {
                "stageName": "Deploy",
                "latestExecution": {"status": "InProgress"},
                "actionStates": [],
            }
        ]
    }

    # Simulate elapsed time > timeout
    times = [0.0, 100.0, 100.0]

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client", return_value=mock_client
        ),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = watch_pipeline_workflow(
            target_dir=configured_workspace,
            execution_id="exec-running-111",
            timeout_seconds=50,
            sleeper=lambda _: None,
            time_provider=lambda: times.pop(0),
        )

    assert result.status == "TimedOut"
    assert "Watch timed out" in (result.error_message or "")
