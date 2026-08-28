"""Tests for AWS CodeBuild and CloudWatch Logs diagnostic utilities."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from lza_workbench.aws.codebuild import (
    extract_log_error_diagnostics,
    fetch_codebuild_diagnostics,
    get_cloudwatch_log_events,
    get_codebuild_build_info,
)


def test_extract_log_error_diagnostics_from_pipeline_fail_log() -> None:
    import pytest

    log_path = Path(__file__).parents[2] / "pipeline-fail.log"
    if not log_path.exists():
        pytest.skip("pipeline-fail.log not present in workspace")
    lines = log_path.read_text(encoding="utf-8").splitlines()

    extracted = extract_log_error_diagnostics(lines)
    assert len(extracted) > 0

    combined = " ".join(extracted)
    assert "ValidationError" in combined
    assert "cannot be deleted while TerminationProtection is enabled" in combined
    assert "AWSAccelerator-PrepareStack-376564958706-eu-west-1" in combined


def test_extract_log_error_diagnostics_synthetic_lines() -> None:
    sample_lines = [
        "[Container] 2026/08/23 Phase complete: DOWNLOAD_SOURCE State: SUCCEEDED",
        "[Container] 2026/08/23 ❌ AWSAccelerator failed: ValidationError: Stack cannot be deleted",
        "error Command failed with exit code 1.",
        "[Container] 2026/08/23 Phase complete: BUILD State: FAILED",
    ]

    extracted = extract_log_error_diagnostics(sample_lines)
    assert len(extracted) >= 1
    assert any("ValidationError: Stack cannot be deleted" in line for line in extracted)


def test_get_codebuild_build_info_success() -> None:
    mock_client = MagicMock()
    mock_client.batch_get_builds.return_value = {
        "builds": [
            {
                "id": "AWSAccelerator-ToolkitProject:12345",
                "buildStatus": "FAILED",
                "logs": {
                    "groupName": "/aws/codebuild/AWSAccelerator-ToolkitProject",
                    "streamName": "12345",
                },
            }
        ]
    }

    info = get_codebuild_build_info(
        client=mock_client,
        build_id="AWSAccelerator-ToolkitProject:12345",
    )
    assert info.get("buildStatus") == "FAILED"
    assert info.get("logs", {}).get("groupName") == "/aws/codebuild/AWSAccelerator-ToolkitProject"


def test_get_cloudwatch_log_events_success() -> None:
    mock_logs = MagicMock()
    mock_logs.get_log_events.return_value = {
        "events": [
            {"message": "Starting build..."},
            {"message": "❌  Error: Something went wrong"},
        ]
    }

    events = get_cloudwatch_log_events(
        logs_client=mock_logs,
        log_group_name="/aws/codebuild/test",
        log_stream_name="stream-1",
    )
    assert len(events) == 2
    assert "Error: Something went wrong" in events[1]


def test_fetch_codebuild_diagnostics_with_cloudwatch() -> None:
    mock_factory = MagicMock()
    mock_codebuild = MagicMock()
    mock_logs = MagicMock()

    mock_codebuild.batch_get_builds.return_value = {
        "builds": [
            {
                "id": "build-123",
                "logs": {
                    "groupName": "/aws/codebuild/project",
                    "streamName": "build-123",
                },
            }
        ]
    }
    mock_logs.get_log_events.return_value = {
        "events": [
            {
                "message": (
                    "2026-08-23 | error | toolkit | Deployment of Stack failed: "
                    "❌  ValidationError: Stack cannot be deleted"
                )
            }
        ]
    }

    def get_client(service: str) -> MagicMock:
        if service == "codebuild":
            return mock_codebuild
        if service == "logs":
            return mock_logs
        return MagicMock()

    mock_factory.get_client.side_effect = get_client

    diagnostics = fetch_codebuild_diagnostics(
        factory=mock_factory,
        build_id="build-123",
    )
    assert len(diagnostics) == 1
    assert "ValidationError: Stack cannot be deleted" in diagnostics[0]


def test_fetch_codebuild_diagnostics_fallback_to_phases() -> None:
    mock_factory = MagicMock()
    mock_codebuild = MagicMock()

    mock_codebuild.batch_get_builds.return_value = {
        "builds": [
            {
                "id": "build-456",
                "logs": {},  # No CloudWatch logs
                "phases": [
                    {
                        "phaseType": "BUILD",
                        "phaseStatus": "FAILED",
                        "contexts": [
                            {
                                "statusCode": "COMMAND_EXECUTION_ERROR",
                                "message": "Command exit status 1",
                            }
                        ],
                    }
                ],
            }
        ]
    }

    mock_factory.get_client.return_value = mock_codebuild

    diagnostics = fetch_codebuild_diagnostics(
        factory=mock_factory,
        build_id="build-456",
    )
    assert len(diagnostics) == 1
    assert diagnostics[0] == "Command exit status 1"


def test_extract_log_error_diagnostics_wrapper_suppression_and_deduplication() -> None:
    raw_logs = [
        "[Container] 2026/08/23 16:47:44.027 | error | toolkit | Deployment of Stack failed: "
        "❌  AWSAccelerator-PrepareStack-123 failed: ValidationError: Stack cannot be deleted",
        "❌  AWSAccelerator-PrepareStack-123 failed: ValidationError: Stack cannot be deleted",
        "ValidationError: Stack cannot be deleted",
        "error Command failed with exit code 1.",
        "Error while executing command: yarn run ts-node ...",
        "Phase context status code: COMMAND_EXECUTION_ERROR",
        "npm ERR! code 1",
    ]

    extracted = extract_log_error_diagnostics(raw_logs)
    # High priority error should be extracted and deduplicated into 1 rich message
    assert len(extracted) == 1
    expected_msg = (
        "AWSAccelerator-PrepareStack-123 failed: ValidationError: Stack cannot be deleted"
    )
    assert expected_msg in extracted[0]
    # Buildspec wrapper noise should not be present

    assert not any("COMMAND_EXECUTION_ERROR" in line for line in extracted)
    assert not any("yarn run" in line for line in extracted)
    assert not any("npm ERR" in line for line in extracted)

