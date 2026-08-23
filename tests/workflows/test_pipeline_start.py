"""Tests for pipeline_start workflow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

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
