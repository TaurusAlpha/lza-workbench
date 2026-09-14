"""Tests for resetting installer settings to deployed configuration."""

from __future__ import annotations

from pathlib import Path

import pytest

from lza_workbench.errors import LzaError
from lza_workbench.installer.initialize import (
    InstallerSettingsRequest,
    apply_installer_settings,
)
from lza_workbench.installer.reset import reset_installer_settings
from lza_workbench.workspace.persistence import (
    load_workspace_config,
    load_workspace_state,
    write_workspace_config,
    write_workspace_state,
)
from lza_workbench.workspace.schema import (
    AwsConfig,
    CustomerConfig,
    LzaConfig,
    WorkspaceConfig,
    WorkspaceState,
)


def test_reset_installer_settings_reverts_to_deployed_parameters(tmp_path: Path) -> None:
    """Resetting installer settings rewrites workspace config to deployed parameters and clears pending."""
    ws_dir = tmp_path / "reset-ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / ".lza").mkdir(parents=True, exist_ok=True)
    (ws_dir / "aws-accelerator-config").mkdir(parents=True, exist_ok=True)

    config = WorkspaceConfig(
        customer=CustomerConfig(name="Reset Test", slug="reset-test"),
        aws=AwsConfig(profile="default", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0"),
    )
    config.installer.options.management_account_email = "mgmt@example.com"
    config.installer.options.log_archive_account_email = "log@example.com"
    config.installer.options.audit_account_email = "audit@example.com"
    config.installer.options.enable_approval_stage = False
    write_workspace_config(ws_dir, config)

    state = WorkspaceState.from_config(config)
    state.installer.deployed_parameters = {
        "EnableApprovalStage": "No",
        "AcceleratorPrefix": "AWSAccelerator",
        "ManagementAccountEmail": "mgmt@example.com",
        "LogArchiveAccountEmail": "log@example.com",
        "AuditAccountEmail": "audit@example.com",
    }
    write_workspace_state(ws_dir, state)

    # Apply changes creating pending deployment parameters
    apply_installer_settings(
        InstallerSettingsRequest(
            target_dir=ws_dir,
            values={
                "EnableApprovalStage": "Yes",
                "ApprovalStageNotifyEmailList": "ops@example.com",
            },
        )
    )

    modified_config = load_workspace_config(ws_dir)
    assert modified_config.installer.options.enable_approval_stage is True
    modified_state = load_workspace_state(ws_dir)
    assert modified_state.installer.pending_parameters is not None

    # Now reset back to deployed parameters
    result = reset_installer_settings(target_dir=ws_dir)

    assert result.resolved_parameters.get("EnableApprovalStage") == "No"

    # Verify workspace config was rewritten back
    restored_config = load_workspace_config(ws_dir)
    assert restored_config.installer.options.enable_approval_stage is False

    # Verify state pending_parameters was cleared
    restored_state = load_workspace_state(ws_dir)
    assert restored_state.installer.pending_parameters is None


def test_reset_installer_settings_no_deployed_parameters_raises(tmp_path: Path) -> None:
    """Resetting fails if no deployed stack parameters exist in AWS or recorded state."""
    ws_dir = tmp_path / "reset-ws-no-deployed"
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / ".lza").mkdir(parents=True, exist_ok=True)
    (ws_dir / "aws-accelerator-config").mkdir(parents=True, exist_ok=True)

    config = WorkspaceConfig(
        customer=CustomerConfig(name="Reset Test", slug="reset-test"),
        aws=AwsConfig(profile="default", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0"),
    )
    config.installer.options.management_account_email = "mgmt@example.com"
    config.installer.options.log_archive_account_email = "log@example.com"
    config.installer.options.audit_account_email = "audit@example.com"
    write_workspace_config(ws_dir, config)

    state = WorkspaceState.from_config(config)
    write_workspace_state(ws_dir, state)

    with pytest.raises(LzaError, match="No deployed CloudFormation stack parameters found"):
        reset_installer_settings(target_dir=ws_dir)
