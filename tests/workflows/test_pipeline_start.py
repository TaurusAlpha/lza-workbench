"""Tests for pipeline_start workflow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lza_workbench.errors import LzaError
from lza_workbench.workflows.pipeline_start import (
    PipelineStartResult,
    start_pipeline_workflow,
)
from lza_workbench.workspace.state import load_workspace_state


def test_start_pipeline_dry_run(configured_workspace: Path) -> None:
    result = start_pipeline_workflow(
        target_dir=configured_workspace,
        dry_run=True,
    )
    assert isinstance(result, PipelineStartResult)
    assert result.dry_run is True
    assert result.execution_id is None
    assert result.pipeline_name == "AWSAccelerator-Pipeline"


def test_start_pipeline_success(configured_workspace: Path) -> None:
    mock_client = MagicMock()
    mock_client.start_pipeline_execution.return_value = {"pipelineExecutionId": "exec-abc-123"}

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client", return_value=mock_client
        ),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = start_pipeline_workflow(
            target_dir=configured_workspace,
            dry_run=False,
        )

    assert result.dry_run is False
    assert result.execution_id == "exec-abc-123"
    assert result.pipeline_name == "AWSAccelerator-Pipeline"

    state = load_workspace_state(configured_workspace)
    assert state.config_pipeline_execution_id == "exec-abc-123"


def test_start_pipeline_installer_type(configured_workspace: Path) -> None:
    mock_client = MagicMock()
    mock_client.start_pipeline_execution.return_value = {"pipelineExecutionId": "exec-inst-456"}

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client", return_value=mock_client
        ),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = start_pipeline_workflow(
            target_dir=configured_workspace,
            pipeline_type="installer",
            dry_run=False,
        )

    assert result.execution_id == "exec-inst-456"
    assert result.pipeline_name == "AWSAccelerator-Installer"

    state = load_workspace_state(configured_workspace)
    assert state.installer_pipeline_execution_id == "exec-inst-456"
    assert state.installer_pipeline_name == "AWSAccelerator-Installer"


def test_start_pipeline_records_explicit_pipeline_name(configured_workspace: Path) -> None:
    mock_client = MagicMock()
    mock_client.get_pipeline_state.return_value = {"stageStates": []}
    mock_client.start_pipeline_execution.return_value = {"pipelineExecutionId": "exec-custom-456"}

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client", return_value=mock_client
        ),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = start_pipeline_workflow(
            target_dir=configured_workspace,
            pipeline_name="Customer-Configuration-Pipeline",
        )

    assert result.pipeline_name == "Customer-Configuration-Pipeline"
    state = load_workspace_state(configured_workspace)
    assert state.config_pipeline_execution_id == "exec-custom-456"
    assert state.config_pipeline_name == "Customer-Configuration-Pipeline"


def test_start_pipeline_blocks_concurrent_execution(configured_workspace: Path) -> None:
    mock_client = MagicMock()
    mock_client.get_pipeline_state.return_value = {
        "stageStates": [
            {
                "stageName": "Deploy",
                "latestExecution": {"status": "InProgress"},
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
        with pytest.raises(LzaError, match="already has an execution in progress"):
            start_pipeline_workflow(target_dir=configured_workspace)

    mock_client.start_pipeline_execution.assert_not_called()


def test_start_pipeline_allows_concurrent_execution_when_requested(
    configured_workspace: Path,
) -> None:
    mock_client = MagicMock()
    mock_client.start_pipeline_execution.return_value = {"pipelineExecutionId": "exec-concurrent"}

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client", return_value=mock_client
        ),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = start_pipeline_workflow(
            target_dir=configured_workspace,
            allow_concurrent=True,
        )

    assert result.execution_id == "exec-concurrent"
    mock_client.get_pipeline_state.assert_not_called()


def test_start_pipeline_reports_execution_id_when_state_save_fails(
    configured_workspace: Path,
) -> None:
    mock_client = MagicMock()
    mock_client.start_pipeline_execution.return_value = {"pipelineExecutionId": "exec-lost"}

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.aws.client_factory.AwsClientFactory.get_client", return_value=mock_client
        ),
        patch(
            "lza_workbench.workflows.pipeline_start.write_workspace_state",
            side_effect=OSError("disk full"),
        ),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        with pytest.raises(LzaError, match="exec-lost"):
            start_pipeline_workflow(target_dir=configured_workspace)
