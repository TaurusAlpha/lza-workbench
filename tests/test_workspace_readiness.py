"""Tests for workspace readiness levels, context loading, and early validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from lza_workbench.errors import LzaError
from lza_workbench.workspace.config import write_workspace_config
from lza_workbench.workspace.context import (
    WorkspaceReadinessLevel,
    evaluate_workspace_readiness,
    load_workspace_context,
)
from lza_workbench.workspace.models import (
    AwsConfig,
    CustomerConfig,
    LzaConfig,
    WorkspaceConfig,
    WorkspaceState,
)
from lza_workbench.workspace.state import write_workspace_state


def create_minimal_workspace(
    tmp_path: Path,
    *,
    profile: str = "test-profile",
    region: str = "us-east-1",
    has_config_dir: bool = True,
    has_installer_params: bool = False,
    installer_stack_id: str | None = None,
) -> Path:
    """Helper to construct a workspace at various readiness levels for testing."""
    ws_dir = tmp_path / "test-workspace"
    ws_dir.mkdir(parents=True, exist_ok=True)

    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile=profile, region=region),
        lza=LzaConfig(version="v1.16.0", accelerator_prefix="AWSAccelerator"),
    )

    if has_installer_params:
        config.installer.source_code.repository_type = "codecommit"
        config.installer.source_code.repository_name = "test-repo"
        config.installer.options.management_account_email = "mgmt@example.com"
        config.installer.options.log_archive_account_email = "log@example.com"
        config.installer.options.audit_account_email = "audit@example.com"

    state = WorkspaceState(installer_stack_id=installer_stack_id)

    if has_config_dir:
        (ws_dir / config.configuration.local_path).mkdir(parents=True, exist_ok=True)

    (ws_dir / ".lza").mkdir(parents=True, exist_ok=True)

    write_workspace_config(ws_dir, config)
    write_workspace_state(ws_dir, state)

    return ws_dir


def test_readiness_level_enum_ordering():
    assert WorkspaceReadinessLevel.UNINITIALIZED < WorkspaceReadinessLevel.CORE_CONFIGURED
    assert WorkspaceReadinessLevel.CORE_CONFIGURED < WorkspaceReadinessLevel.IMPORTED
    assert WorkspaceReadinessLevel.IMPORTED < WorkspaceReadinessLevel.CONFIGURED
    assert WorkspaceReadinessLevel.CONFIGURED < WorkspaceReadinessLevel.DEPLOYED


@pytest.mark.parametrize(
    ("has_core_config", "has_config_dir", "has_installer_params", "installer_stack_id", "expected"),
    [
        (False, False, False, None, WorkspaceReadinessLevel.UNINITIALIZED),
        (True, False, False, None, WorkspaceReadinessLevel.CORE_CONFIGURED),
        (True, True, False, None, WorkspaceReadinessLevel.IMPORTED),
        (True, True, True, None, WorkspaceReadinessLevel.CONFIGURED),
        (True, True, True, "stack-id", WorkspaceReadinessLevel.DEPLOYED),
    ],
)
def test_evaluate_workspace_readiness_transitions(
    tmp_path: Path,
    has_core_config: bool,
    has_config_dir: bool,
    has_installer_params: bool,
    installer_stack_id: str | None,
    expected: WorkspaceReadinessLevel,
) -> None:
    """Each row describes the minimum state required for one readiness level."""
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()
    config = WorkspaceConfig(
        customer=CustomerConfig(
            name="Test Customer" if has_core_config else "",
            slug="test-customer" if has_core_config else "",
        ),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0", accelerator_prefix="AWSAccelerator"),
    )
    if has_config_dir:
        (ws_dir / config.configuration.local_path).mkdir()
    if has_installer_params:
        config.installer.source_code.repository_type = "codecommit"
        config.installer.source_code.repository_name = "test-repo"
        config.installer.options.management_account_email = "mgmt@example.com"
        config.installer.options.log_archive_account_email = "log@example.com"
        config.installer.options.audit_account_email = "audit@example.com"

    state = WorkspaceState(installer_stack_id=installer_stack_id)

    assert evaluate_workspace_readiness(ws_dir, config, state) == expected


def test_load_workspace_context_success(tmp_path: Path):
    ws_dir = create_minimal_workspace(tmp_path, has_config_dir=True, has_installer_params=True)
    ctx = load_workspace_context(ws_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED)
    assert ctx.workspace_dir == ws_dir.resolve()
    assert ctx.config.customer.slug == "test-customer"
    assert ctx.readiness_level >= WorkspaceReadinessLevel.CONFIGURED


def test_load_workspace_context_fails_when_below_min_readiness(tmp_path: Path):
    ws_dir = create_minimal_workspace(tmp_path, has_config_dir=False, has_installer_params=False)
    with pytest.raises(LzaError, match="missing required LZA templates"):
        load_workspace_context(ws_dir, min_readiness=WorkspaceReadinessLevel.IMPORTED)


def test_readiness_uses_shared_installer_validation(tmp_path: Path) -> None:
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()
    (ws_dir / "aws-accelerator-config").mkdir()
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0", accelerator_prefix="AWSAccelerator"),
    )
    config.installer.source_code.repository_type = "codeconnection"
    config.installer.source_code.connection_arn = ""
    config.installer.options.management_account_email = "mgmt@example.com"
    config.installer.options.log_archive_account_email = "log@example.com"
    config.installer.options.audit_account_email = "audit@example.com"

    assert (
        evaluate_workspace_readiness(ws_dir, config, WorkspaceState())
        == WorkspaceReadinessLevel.IMPORTED
    )
