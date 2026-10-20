"""Tests for pipeline_start workflow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lza_workbench.errors import LzaError
from lza_workbench.pipeline.start import (
    PipelineStartResult,
    start_pipeline_workflow,
)
from lza_workbench.workspace.persistence import load_workspace_state


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
        patch("lza_workbench.infrastructure.aws.session.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.infrastructure.aws.session.AwsClientFactory.get_client", return_value=mock_client
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
    assert state.pipelines.configuration.last_operation is not None
    assert state.pipelines.configuration.last_operation.execution_id == "exec-abc-123"
    assert state.pipelines.configuration.observation is None


def test_start_pipeline_installer_type(configured_workspace: Path) -> None:
    mock_client = MagicMock()
    mock_client.start_pipeline_execution.return_value = {"pipelineExecutionId": "exec-inst-456"}

    with (
        patch("lza_workbench.infrastructure.aws.session.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.infrastructure.aws.session.AwsClientFactory.get_client", return_value=mock_client
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
    assert state.pipelines.installer.last_operation is not None
    assert state.pipelines.installer.last_operation.execution_id == "exec-inst-456"
    assert state.pipelines.installer.last_operation.pipeline_name == "AWSAccelerator-Installer"


def test_start_pipeline_records_explicit_pipeline_name(configured_workspace: Path) -> None:
    mock_client = MagicMock()
    mock_client.get_pipeline_state.return_value = {"stageStates": []}
    mock_client.start_pipeline_execution.return_value = {"pipelineExecutionId": "exec-custom-456"}

    with (
        patch("lza_workbench.infrastructure.aws.session.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.infrastructure.aws.session.AwsClientFactory.get_client", return_value=mock_client
        ),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        result = start_pipeline_workflow(
            target_dir=configured_workspace,
            pipeline_name="Customer-Configuration-Pipeline",
        )

    assert result.pipeline_name == "Customer-Configuration-Pipeline"
    state = load_workspace_state(configured_workspace)
    assert state.pipelines.configuration.last_operation is not None
    assert state.pipelines.configuration.last_operation.execution_id == "exec-custom-456"
    assert (
        state.pipelines.configuration.last_operation.pipeline_name
        == "Customer-Configuration-Pipeline"
    )


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
        patch("lza_workbench.infrastructure.aws.session.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.infrastructure.aws.session.AwsClientFactory.get_client", return_value=mock_client
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
        patch("lza_workbench.infrastructure.aws.session.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.infrastructure.aws.session.AwsClientFactory.get_client", return_value=mock_client
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
        patch("lza_workbench.infrastructure.aws.session.AwsClientFactory.validate_identity") as mock_val,
        patch(
            "lza_workbench.infrastructure.aws.session.AwsClientFactory.get_client", return_value=mock_client
        ),
        patch(
            "lza_workbench.pipeline.start.update_workspace_state",
            side_effect=OSError("disk full"),
        ),
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        with pytest.raises(LzaError, match="exec-lost"):
            start_pipeline_workflow(target_dir=configured_workspace)


def test_offline_pipeline_status_reconciles_newer_start_record_without_fabricating_status(
    configured_workspace: Path,
) -> None:
    from datetime import UTC, datetime, timedelta

    from lza_workbench.infrastructure.aws.session import AwsExecutionContext
    from lza_workbench.pipeline.state import PipelineObservation, PipelineOperationRecord
    from lza_workbench.pipeline.status import get_pipeline_status_workflow
    from lza_workbench.workspace.persistence import write_workspace_state

    t0 = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    t1 = t0 + timedelta(minutes=5)
    state = load_workspace_state(configured_workspace)
    state.pipelines.configuration.observation = PipelineObservation(
        pipeline_name="AWSAccelerator-Pipeline",
        execution_id="exec-old-failed",
        status="Failed",
        failed_stage="Deploy",
        failed_action="DeployAction",
        error="Old failure",
        observed_at=t0,
    )
    state.pipelines.configuration.last_operation = PipelineOperationRecord(
        pipeline_name="AWSAccelerator-Pipeline",
        execution_id="exec-new-started",
        action="started",
        recorded_at=t1,
    )
    write_workspace_state(configured_workspace, state)

    offline_aws = AwsExecutionContext(
        region="eu-west-1",
        factory=MagicMock(),
        identity=None,
        error="Offline",
    )
    result = get_pipeline_status_workflow(
        target_dir=configured_workspace,
        aws_context=offline_aws,
    )
    assert result.configuration is not None
    assert result.configuration.is_live is False
    assert result.configuration.latest_execution_id == "exec-new-started"
    assert result.configuration.status is None
    assert result.configuration.failed_stage is None
