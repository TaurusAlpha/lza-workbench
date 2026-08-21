"""Tests for installer status calculations (configuration drift & state alignment)."""

from __future__ import annotations

from lza_workbench.installer.status import (
    calculate_configuration_drift,
    calculate_state_alignment,
)
from lza_workbench.workspace.schema import (
    AwsConfig,
    CustomerConfig,
    WorkspaceConfig,
    WorkspaceState,
)


def test_calculate_configuration_drift_returns_only_changed_parameters() -> None:
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
    )

    drift = calculate_configuration_drift(
        config,
        {
            "RepositorySource": "github",
            "RepositoryOwner": "awslabs",
            "RepositoryName": "landing-zone-accelerator-on-aws",
            "RepositoryBranchName": "release/v1.15.5",
            "EnableApprovalStage": "Yes",
        },
    )

    assert drift["EnableApprovalStage"] == ("Yes", "No")
    assert "RepositorySource" not in drift


def test_calculate_state_alignment_compares_stack_and_version_metadata() -> None:
    state = WorkspaceState(
        installer_stack_id="stack-id",
        installer_stack_status="CREATE_COMPLETE",
        installer_template_version="v1.15.5",
    )

    aligned = calculate_state_alignment(
        state,
        stack_id="stack-id",
        stack_status="CREATE_COMPLETE",
        deployed_version="release/v1.15.5",
    )
    stale = calculate_state_alignment(
        state,
        stack_id="stack-id",
        stack_status="UPDATE_COMPLETE",
        deployed_version="v1.15.5",
    )

    assert aligned.in_sync is True
    assert stale.in_sync is False
