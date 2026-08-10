"""Tests for workspace readiness levels, context loading, and early validation."""

from __future__ import annotations

from pathlib import Path

import pytest
import typer

from lza_workbench.core.workspace import (
    WORKSPACE_CONFIG_FILE,
    WORKSPACE_STATE_FILE,
    AwsConfig,
    CustomerConfig,
    LzaConfig,
    WorkspaceConfig,
    WorkspaceReadinessLevel,
    WorkspaceState,
    evaluate_workspace_readiness,
    load_workspace_config,
    load_workspace_context,
    load_workspace_state,
    write_workspace_config,
    write_workspace_state,
)


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

    write_workspace_config(ws_dir / WORKSPACE_CONFIG_FILE, config)
    write_workspace_state(ws_dir / WORKSPACE_STATE_FILE, state)

    return ws_dir


def test_readiness_level_enum_ordering():
    assert WorkspaceReadinessLevel.UNINITIALIZED < WorkspaceReadinessLevel.CORE_CONFIGURED
    assert WorkspaceReadinessLevel.CORE_CONFIGURED < WorkspaceReadinessLevel.IMPORTED
    assert WorkspaceReadinessLevel.IMPORTED < WorkspaceReadinessLevel.CONFIGURED
    assert WorkspaceReadinessLevel.CONFIGURED < WorkspaceReadinessLevel.DEPLOYED


def test_evaluate_uninitialized(tmp_path: Path):
    ws_dir = tmp_path / "empty"
    ws_dir.mkdir()
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test", slug="test"),
        aws=AwsConfig(profile="", region="us-east-1"),
    )
    state = WorkspaceState()
    assert (
        evaluate_workspace_readiness(ws_dir, config, state)
        == WorkspaceReadinessLevel.UNINITIALIZED
    )


def test_evaluate_core_configured(tmp_path: Path):
    ws_dir = create_minimal_workspace(tmp_path, has_config_dir=False)
    config = load_workspace_config(ws_dir / WORKSPACE_CONFIG_FILE)
    state = load_workspace_state(ws_dir / WORKSPACE_STATE_FILE)

    assert (
        evaluate_workspace_readiness(ws_dir, config, state)
        == WorkspaceReadinessLevel.CORE_CONFIGURED
    )


def test_evaluate_imported(tmp_path: Path):
    ws_dir = create_minimal_workspace(tmp_path, has_config_dir=True, has_installer_params=False)
    config = load_workspace_config(ws_dir / WORKSPACE_CONFIG_FILE)
    state = load_workspace_state(ws_dir / WORKSPACE_STATE_FILE)

    assert evaluate_workspace_readiness(ws_dir, config, state) == WorkspaceReadinessLevel.IMPORTED


def test_evaluate_configured(tmp_path: Path):
    ws_dir = create_minimal_workspace(tmp_path, has_config_dir=True, has_installer_params=True)
    config = load_workspace_config(ws_dir / WORKSPACE_CONFIG_FILE)
    state = load_workspace_state(ws_dir / WORKSPACE_STATE_FILE)

    assert evaluate_workspace_readiness(ws_dir, config, state) == WorkspaceReadinessLevel.CONFIGURED


def test_evaluate_deployed(tmp_path: Path):
    ws_dir = create_minimal_workspace(
        tmp_path,
        has_config_dir=True,
        has_installer_params=True,
        installer_stack_id="arn:aws:cloudformation:us-east-1:123456789012:stack/test/123",
    )
    config = load_workspace_config(ws_dir / WORKSPACE_CONFIG_FILE)
    state = load_workspace_state(ws_dir / WORKSPACE_STATE_FILE)

    assert evaluate_workspace_readiness(ws_dir, config, state) == WorkspaceReadinessLevel.DEPLOYED


def test_load_workspace_context_success(tmp_path: Path):
    ws_dir = create_minimal_workspace(tmp_path, has_config_dir=True, has_installer_params=True)
    ctx = load_workspace_context(ws_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED)
    assert ctx.workspace_dir == ws_dir.resolve()
    assert ctx.config.customer.slug == "test-customer"
    assert ctx.readiness_level >= WorkspaceReadinessLevel.CONFIGURED


def test_load_workspace_context_fails_when_below_min_readiness(tmp_path: Path):
    ws_dir = create_minimal_workspace(tmp_path, has_config_dir=False, has_installer_params=False)
    with pytest.raises(typer.BadParameter, match="missing required LZA templates"):
        load_workspace_context(ws_dir, min_readiness=WorkspaceReadinessLevel.IMPORTED)
