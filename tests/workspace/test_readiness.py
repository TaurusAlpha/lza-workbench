"""Tests for workspace capability assessment and context validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from lza_workbench.errors import LzaError
from lza_workbench.workspace.config import write_workspace_config
from lza_workbench.workspace.context import (
    WorkspaceCapability,
    evaluate_workspace_assessment,
    load_workspace_context,
    require_capabilities,
)
from lza_workbench.workspace.schema import (
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
    imported: bool | None = None,
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

    state = WorkspaceState(installer_stack_id=installer_stack_id, imported=imported)

    if has_config_dir:
        (ws_dir / config.configuration.local_path).mkdir(parents=True, exist_ok=True)

    (ws_dir / ".lza").mkdir(parents=True, exist_ok=True)

    write_workspace_config(ws_dir, config)
    write_workspace_state(ws_dir, state)

    return ws_dir


@pytest.mark.parametrize(
    (
        "has_core_config",
        "has_config_dir",
        "has_installer_params",
        "installer_stack_id",
        "imported",
        "expected",
    ),
    [
        (False, False, False, None, False, (False, False, False, False, False)),
        (True, False, False, None, True, (True, False, False, False, True)),
        (True, True, False, None, False, (True, True, False, False, False)),
        (True, True, True, None, False, (True, True, True, False, False)),
        (True, True, True, "stack-id", True, (True, True, True, True, True)),
    ],
)
def test_evaluate_workspace_assessment(
    tmp_path: Path,
    has_core_config: bool,
    has_config_dir: bool,
    has_installer_params: bool,
    installer_stack_id: str | None,
    imported: bool,
    expected: tuple[bool, bool, bool, bool, bool],
) -> None:
    """Each capability is evaluated independently from config, filesystem, and state."""
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

    state = WorkspaceState(installer_stack_id=installer_stack_id, imported=imported)

    assessment = evaluate_workspace_assessment(ws_dir, config, state)
    assert (
        assessment.metadata_valid,
        assessment.configuration_present,
        assessment.installer_configured,
        assessment.installer_recorded_deployed,
        assessment.imported,
    ) == expected


def test_load_workspace_context_success(tmp_path: Path) -> None:
    ws_dir = create_minimal_workspace(tmp_path, has_config_dir=True, has_installer_params=True)
    ctx = load_workspace_context(ws_dir)
    assert ctx.workspace_dir == ws_dir.resolve()
    assert ctx.config.customer.slug == "test-customer"
    assert ctx.assessment.installer_configured


def test_load_workspace_context_fails_when_below_min_readiness(tmp_path: Path) -> None:
    ws_dir = create_minimal_workspace(tmp_path, has_config_dir=False, has_installer_params=False)
    with pytest.raises(LzaError, match="missing required LZA templates"):
        load_workspace_context(
            ws_dir,
            required_capabilities=(
                WorkspaceCapability.METADATA_VALID,
                WorkspaceCapability.CONFIGURATION_PRESENT,
            ),
        )


@pytest.mark.parametrize(
    ("required_capabilities", "expected_error"),
    [
        ((WorkspaceCapability.METADATA_VALID,), "missing required core configuration"),
        (
            (
                WorkspaceCapability.METADATA_VALID,
                WorkspaceCapability.CONFIGURATION_PRESENT,
            ),
            "missing required LZA templates",
        ),
        (
            (
                WorkspaceCapability.METADATA_VALID,
                WorkspaceCapability.CONFIGURATION_PRESENT,
                WorkspaceCapability.INSTALLER_CONFIGURED,
            ),
            "missing required installer configuration parameters",
        ),
        (
            (
                WorkspaceCapability.METADATA_VALID,
                WorkspaceCapability.CONFIGURATION_PRESENT,
                WorkspaceCapability.INSTALLER_CONFIGURED,
                WorkspaceCapability.INSTALLER_RECORDED_DEPLOYED,
            ),
            "Installer CloudFormation stack has not been deployed",
        ),
    ],
)
def test_require_capabilities_preserves_readiness_errors(
    tmp_path: Path,
    required_capabilities: tuple[WorkspaceCapability, ...],
    expected_error: str,
) -> None:
    ws_dir = create_minimal_workspace(
        tmp_path,
        has_config_dir=False,
        has_installer_params=False,
    )
    context = load_workspace_context(ws_dir)
    assessment = context.assessment

    if required_capabilities == (WorkspaceCapability.METADATA_VALID,):
        context.config.customer.slug = ""
        assessment = evaluate_workspace_assessment(ws_dir, context.config, context.state)
    if WorkspaceCapability.INSTALLER_CONFIGURED in required_capabilities:
        (ws_dir / context.config.configuration.local_path).mkdir()
        assessment = evaluate_workspace_assessment(ws_dir, context.config, context.state)
    if WorkspaceCapability.INSTALLER_RECORDED_DEPLOYED in required_capabilities:
        context.config.installer.source_code.repository_type = "codecommit"
        context.config.installer.source_code.repository_name = "test-repo"
        context.config.installer.options.management_account_email = "mgmt@example.com"
        context.config.installer.options.log_archive_account_email = "log@example.com"
        context.config.installer.options.audit_account_email = "audit@example.com"
        assessment = evaluate_workspace_assessment(ws_dir, context.config, context.state)

    with pytest.raises(LzaError, match=expected_error):
        require_capabilities(
            assessment,
            *required_capabilities,
            workspace_dir=ws_dir,
            config=context.config,
        )


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
        not evaluate_workspace_assessment(ws_dir, config, WorkspaceState()).installer_configured
    )


def test_workspace_context_path_properties(tmp_path: Path) -> None:
    ws_dir = create_minimal_workspace(tmp_path)
    ctx = load_workspace_context(ws_dir)

    assert ctx.config_dir == ws_dir / "aws-accelerator-config"
    assert ctx.installer_dir == ws_dir / "aws-accelerator-installer"
    assert ctx.state_dir == ws_dir / ".lza"
    assert ctx.config_file == ws_dir / "lza-workspace.yaml"
    assert ctx.state_file == ws_dir / ".lza" / "state.json"
