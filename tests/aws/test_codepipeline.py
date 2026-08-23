"""Tests for AWS CodePipeline integration adapter."""

from __future__ import annotations

from unittest.mock import MagicMock

from botocore.exceptions import ClientError

from lza_workbench.aws.codepipeline import (
    PipelineStateResult,
    get_pipeline_state,
)


def test_get_pipeline_state_no_client() -> None:
    result = get_pipeline_state(client=None, pipeline_name="AWSAccelerator-Installer")
    assert isinstance(result, PipelineStateResult)
    assert result.exists is False
    assert result.status == "NOT_CHECKED"


def test_get_pipeline_state_empty_name() -> None:
    result = get_pipeline_state(client=MagicMock(), pipeline_name="")
    assert result.exists is False
    assert result.status == "NOT_SPECIFIED"


def test_get_pipeline_state_not_found() -> None:
    client = MagicMock()
    err_response = {"Error": {"Code": "PipelineNotFoundException", "Message": "Not found"}}
    client.get_pipeline_state.side_effect = ClientError(err_response, "GetPipelineState")

    result = get_pipeline_state(client=client, pipeline_name="AWSAccelerator-Installer")
    assert result.exists is False
    assert result.status == "NOT_DEPLOYED"


def test_get_pipeline_state_succeeded() -> None:
    client = MagicMock()
    client.get_pipeline_state.return_value = {
        "pipelineName": "AWSAccelerator-Installer",
        "stageStates": [
            {
                "stageName": "Source",
                "latestExecution": {
                    "pipelineExecutionId": "exec-123",
                    "status": "Succeeded",
                },
                "actionStates": [
                    {
                        "actionName": "SourceAction",
                        "latestExecution": {
                            "status": "Succeeded",
                            "summary": "Success summary",
                        },
                    }
                ],
            },
            {
                "stageName": "Deploy",
                "latestExecution": {
                    "pipelineExecutionId": "exec-123",
                    "status": "Succeeded",
                },
                "actionStates": [],
            },
        ],
    }

    result = get_pipeline_state(client=client, pipeline_name="AWSAccelerator-Installer")
    assert result.exists is True
    assert result.status == "Succeeded"
    assert result.latest_execution_id == "exec-123"
    assert len(result.stage_states) == 2
    assert result.stage_states[0].stage_name == "Source"
    assert result.stage_states[0].status == "Succeeded"
    assert len(result.stage_states[0].actions) == 1
    assert result.stage_states[0].actions[0].action_name == "SourceAction"


def test_get_pipeline_state_in_progress() -> None:
    client = MagicMock()
    client.get_pipeline_state.return_value = {
        "pipelineName": "AWSAccelerator-Installer",
        "stageStates": [
            {
                "stageName": "Source",
                "latestExecution": {
                    "pipelineExecutionId": "exec-456",
                    "status": "Succeeded",
                },
            },
            {
                "stageName": "Deploy",
                "latestExecution": {
                    "pipelineExecutionId": "exec-456",
                    "status": "InProgress",
                },
            },
        ],
    }

    result = get_pipeline_state(client=client, pipeline_name="AWSAccelerator-Installer")
    assert result.exists is True
    assert result.status == "InProgress"


def test_get_pipeline_state_failed() -> None:
    client = MagicMock()
    client.get_pipeline_state.return_value = {
        "pipelineName": "AWSAccelerator-Installer",
        "stageStates": [
            {
                "stageName": "Source",
                "latestExecution": {
                    "pipelineExecutionId": "exec-789",
                    "status": "Failed",
                },
            },
        ],
    }

    result = get_pipeline_state(client=client, pipeline_name="AWSAccelerator-Installer")
    assert result.exists is True
    assert result.status == "Failed"


def test_start_pipeline_execution_success() -> None:
    from lza_workbench.aws.codepipeline import start_pipeline_execution

    client = MagicMock()
    client.start_pipeline_execution.return_value = {"pipelineExecutionId": "exec-abc"}

    exec_id = start_pipeline_execution(client=client, pipeline_name="AWSAccelerator-Pipeline")
    assert exec_id == "exec-abc"
    client.start_pipeline_execution.assert_called_once_with(name="AWSAccelerator-Pipeline")


def test_start_pipeline_execution_empty_name() -> None:
    import pytest

    from lza_workbench.aws.codepipeline import start_pipeline_execution
    from lza_workbench.errors import LzaError

    with pytest.raises(LzaError, match="Pipeline name cannot be empty"):
        start_pipeline_execution(client=MagicMock(), pipeline_name="")


def test_start_pipeline_execution_not_found() -> None:
    import pytest

    from lza_workbench.aws.codepipeline import start_pipeline_execution
    from lza_workbench.errors import LzaError

    client = MagicMock()
    err_response = {"Error": {"Code": "PipelineNotFoundException", "Message": "Not found"}}
    client.start_pipeline_execution.side_effect = ClientError(
        err_response, "StartPipelineExecution"
    )

    with pytest.raises(LzaError, match="does not exist"):
        start_pipeline_execution(client=client, pipeline_name="AWSAccelerator-Pipeline")


def test_get_pipeline_execution_success() -> None:
    from lza_workbench.aws.codepipeline import get_pipeline_execution

    client = MagicMock()
    client.get_pipeline_execution.return_value = {
        "pipelineExecution": {
            "pipelineExecutionId": "exec-123",
            "status": "Succeeded",
            "statusSummary": "Done",
            "startTime": "2026-08-23T10:00:00Z",
            "lastUpdateTime": "2026-08-23T10:15:00Z",
        }
    }

    result = get_pipeline_execution(
        client=client,
        pipeline_name="AWSAccelerator-Pipeline",
        execution_id="exec-123",
    )
    assert result.status == "Succeeded"
    assert result.execution_id == "exec-123"
    assert result.status_summary == "Done"


def test_get_pipeline_execution_not_found() -> None:
    from lza_workbench.aws.codepipeline import get_pipeline_execution

    client = MagicMock()
    err_response = {
        "Error": {"Code": "PipelineExecutionNotFoundException", "Message": "Exec not found"}
    }
    client.get_pipeline_execution.side_effect = ClientError(err_response, "GetPipelineExecution")

    result = get_pipeline_execution(
        client=client,
        pipeline_name="AWSAccelerator-Pipeline",
        execution_id="exec-999",
    )
    assert result.status == "NOT_FOUND"


def test_get_latest_pipeline_execution_id() -> None:
    from lza_workbench.aws.codepipeline import get_latest_pipeline_execution_id

    client = MagicMock()
    client.list_pipeline_executions.return_value = {
        "pipelineExecutionSummaries": [{"pipelineExecutionId": "exec-latest"}]
    }

    exec_id = get_latest_pipeline_execution_id(
        client=client,
        pipeline_name="AWSAccelerator-Pipeline",
    )
    assert exec_id == "exec-latest"

