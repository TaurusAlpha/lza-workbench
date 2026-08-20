"""Tests for AWS CodePipeline integration adapter."""

from __future__ import annotations

from unittest.mock import MagicMock

from botocore.exceptions import ClientError

from lza_workbench.aws.codepipeline import (
    PipelineStateResult,
    get_pipeline_state,
)


def test_get_pipeline_state_no_client():
    result = get_pipeline_state(client=None, pipeline_name="AWSAccelerator-Installer")
    assert isinstance(result, PipelineStateResult)
    assert result.exists is False
    assert result.status == "NOT_CHECKED"


def test_get_pipeline_state_empty_name():
    result = get_pipeline_state(client=MagicMock(), pipeline_name="")
    assert result.exists is False
    assert result.status == "NOT_SPECIFIED"


def test_get_pipeline_state_not_found():
    client = MagicMock()
    err_response = {"Error": {"Code": "PipelineNotFoundException", "Message": "Not found"}}
    client.get_pipeline_state.side_effect = ClientError(err_response, "GetPipelineState")

    result = get_pipeline_state(client=client, pipeline_name="AWSAccelerator-Installer")
    assert result.exists is False
    assert result.status == "NOT_DEPLOYED"


def test_get_pipeline_state_succeeded():
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


def test_get_pipeline_state_in_progress():
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


def test_get_pipeline_state_failed():
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
