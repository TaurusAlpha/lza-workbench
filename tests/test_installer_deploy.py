"""Tests for lza installer deploy command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from pydantic import ValidationError

from lza_workbench.aws.cloudformation import CfnDeploymentPlanResult, CfnStackStatusResult
from lza_workbench.aws.codecommit import CodeCommitPlanResult
from lza_workbench.aws.context import AwsExecutionContext
from lza_workbench.commands.installer_deploy import run_installer_deploy
from lza_workbench.errors import LzaError
from lza_workbench.installer.deployment import (
    inspect_installer_source,
    validate_cloudformation_plan,
)
from lza_workbench.workspace.config import write_workspace_config
from lza_workbench.workspace.models import (
    AwsConfig,
    CustomerConfig,
    LzaConfig,
    WorkspaceConfig,
    WorkspaceState,
)
from lza_workbench.workspace.state import load_workspace_state, write_workspace_state


@pytest.fixture
def sample_workspace(tmp_path: Path) -> Path:
    """Create a sample workspace directory with valid lza-workspace.yaml."""
    ws_dir = tmp_path / "comm-it"
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / ".lza").mkdir(parents=True, exist_ok=True)
    (ws_dir / "aws-accelerator-installer").mkdir(parents=True, exist_ok=True)
    (ws_dir / "aws-accelerator-config").mkdir(parents=True, exist_ok=True)

    config = WorkspaceConfig(
        customer=CustomerConfig(name="Comm IT", slug="comm-it"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0", accelerator_prefix="AWSAccelerator"),
    )
    config.installer.source_code.repository_type = "codecommit"
    config.installer.source_code.repository_name = "aws-accelerator-codecommit"
    config.installer.source_code.branch = "release/v1.16.0"

    config.installer.options.management_account_email = "root@example.com"
    config.installer.options.log_archive_account_email = "log@example.com"
    config.installer.options.audit_account_email = "audit@example.com"

    write_workspace_config(ws_dir, config)
    write_workspace_state(ws_dir, WorkspaceState.from_config(config))

    template_file = ws_dir / "aws-accelerator-installer" / "AWSAccelerator-InstallerStack.template"
    template_file.write_text(
        '{"Description": "Installer", "Parameters": {'
        '"ManagementAccountEmail": {"Type": "String"},'
        '"RepositorySource": {"Type": "String"}'
        "}}",
        encoding="utf-8",
    )

    return ws_dir


def test_missing_aws_profile_failure(tmp_path: Path) -> None:
    """Test that missing AWS profile in lza-workspace.yaml raises an exception."""
    ws_dir = tmp_path / "no-aws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    with pytest.raises(
        (LzaError, ValueError, ValidationError),
        match="missing required core configuration|profile|AWS configuration requires",
    ):
        config = WorkspaceConfig(
            customer=CustomerConfig(name="No AWS", slug="no-aws"),
            aws=AwsConfig(profile="", region="us-east-1"),
            lza=LzaConfig(version="v1.16.0"),
        )
        write_workspace_config(ws_dir, config)
        run_installer_deploy(target_dir=ws_dir)


def test_missing_required_params_failure(tmp_path: Path) -> None:
    """Test that missing required installer parameters stops deployment."""
    ws_dir = tmp_path / "incomplete"
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / "aws-accelerator-config").mkdir(parents=True, exist_ok=True)
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Incomplete", slug="incomplete"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0"),
    )
    write_workspace_config(ws_dir, config)

    with pytest.raises(
        LzaError,
        match="missing required installer configuration parameters|missing from lza-workspace.yaml",
    ):
        run_installer_deploy(target_dir=ws_dir)


@patch("lza_workbench.commands.installer_deploy.resolve_aws_execution_context")
@patch("lza_workbench.commands.installer_deploy.inspect_cloudformation_stack")
def test_installer_deploy_dry_run(
    mock_inspect_cfn: MagicMock,
    mock_resolve_context: MagicMock,
    sample_workspace: Path,
) -> None:
    """Test dry-run deployment does not mutate AWS resources or update state."""
    mock_factory = MagicMock()
    mock_resolve_context.return_value = AwsExecutionContext(
        region="us-east-1",
        factory=mock_factory,
        identity={
            "account": "123456789012",
            "arn": "arn:aws:iam::123456789012:user/admin",
            "user_id": "ADMIN",
        },
        error=None,
    )
    mock_inspect_cfn.return_value = CfnDeploymentPlanResult(
        stack_name="AWSAccelerator-InstallerStack",
        operation="CREATE",
        stack_status=None,
        resolved_parameters={},
    )

    run_installer_deploy(dry_run=True, force=True, target_dir=sample_workspace)

    state = load_workspace_state(sample_workspace)
    assert state.installer_stack_id is None


@patch("lza_workbench.commands.installer_deploy.stream_cloudformation_stack_events")
@patch("lza_workbench.commands.installer_deploy.deploy_cloudformation_stack")
@patch("lza_workbench.commands.installer_deploy.inspect_cloudformation_stack")
@patch("lza_workbench.installer.deployment.inspect_codecommit_repository")
@patch("lza_workbench.commands.installer_deploy.resolve_aws_execution_context")
def test_installer_deploy_success(
    mock_resolve_context: MagicMock,
    mock_inspect_cc: MagicMock,
    mock_inspect_cfn: MagicMock,
    mock_deploy_cfn: MagicMock,
    mock_stream_cfn: MagicMock,
    sample_workspace: Path,
) -> None:
    """Test successful deployment updates workspace state correctly."""
    mock_factory = MagicMock()
    mock_resolve_context.return_value = AwsExecutionContext(
        region="us-east-1",
        factory=mock_factory,
        identity={
            "account": "123456789012",
            "arn": "arn:aws:iam::123456789012:user/admin",
            "user_id": "ADMIN",
        },
        error=None,
    )

    mock_inspect_cc.return_value = CodeCommitPlanResult(
        repository_name="aws-accelerator-codecommit",
        branch_name="release/v1.16.0",
        status="INITIALIZED",
        creation_required=False,
        sync_required=False,
        official_repo_url="",
        official_version_ref="",
    )
    mock_inspect_cfn.return_value = CfnDeploymentPlanResult(
        stack_name="AWSAccelerator-InstallerStack",
        operation="CREATE",
        stack_status=None,
        resolved_parameters={},
    )
    mock_deploy_cfn.return_value = (
        "arn:aws:cloudformation:us-east-1:123456789012:stack/AWSAccelerator-InstallerStack/uuid"
    )
    mock_stream_cfn.return_value = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack",
        exists=True,
        stack_status="CREATE_COMPLETE",
        stack_id="arn:aws:cloudformation:us-east-1:123456789012:stack/AWSAccelerator-InstallerStack/uuid",
        outputs={"PipelineName": "AWSAccelerator-Pipeline"},
    )

    run_installer_deploy(force=True, target_dir=sample_workspace)

    state = load_workspace_state(sample_workspace)
    assert state.installer_stack_status == "CREATE_COMPLETE"
    assert (
        state.installer_stack_id
        == "arn:aws:cloudformation:us-east-1:123456789012:stack/AWSAccelerator-InstallerStack/uuid"
    )
    assert state.management_account_id == "123456789012"


@patch("lza_workbench.installer.deployment.inspect_codecommit_repository")
@patch("lza_workbench.commands.installer_deploy.resolve_aws_execution_context")
def test_installer_deploy_requires_manually_synchronized_codecommit_source(
    mock_resolve_context: MagicMock,
    mock_inspect_cc: MagicMock,
    sample_workspace: Path,
) -> None:
    """An empty CodeCommit repository must not be mistaken for a usable source."""
    mock_resolve_context.return_value = AwsExecutionContext(
        region="us-east-1",
        factory=MagicMock(),
        identity={
            "account": "123456789012",
            "arn": "arn:aws:iam::123456789012:user/admin",
            "user_id": "ADMIN",
        },
        error=None,
    )
    mock_inspect_cc.return_value = CodeCommitPlanResult(
        repository_name="aws-accelerator-codecommit",
        branch_name="release/v1.16.0",
        status="UNINITIALIZED",
        creation_required=False,
        sync_required=True,
        official_repo_url="",
        official_version_ref="",
    )

    with pytest.raises(LzaError, match="manual prerequisite"):
        run_installer_deploy(force=True, target_dir=sample_workspace)


@pytest.mark.parametrize(
    ("operation", "stack_status", "expected"),
    [
        ("CREATE", None, "CREATE"),
        ("UPDATE", "UPDATE_COMPLETE", "UPDATE"),
        ("NO_CHANGE", "CREATE_COMPLETE", "NO_CHANGE"),
    ],
)
def test_cloudformation_plan_accepts_safe_outcomes(
    operation: str, stack_status: str | None, expected: str
) -> None:
    """Create, update, and no-change plans are accepted only from safe states."""
    plan = CfnDeploymentPlanResult(
        stack_name="AWSAccelerator-InstallerStack",
        operation=operation,
        stack_status=stack_status,
        resolved_parameters={},
    )

    assert validate_cloudformation_plan(plan) == expected


@pytest.mark.parametrize(
    ("operation", "stack_status"),
    [("UNKNOWN", "Error: access denied"), ("UPDATE", "UPDATE_IN_PROGRESS")],
)
def test_cloudformation_plan_rejects_inaccessible_or_unsafe_outcomes(
    operation: str, stack_status: str
) -> None:
    """Unknown and transitional states cannot reach CloudFormation mutation."""
    plan = CfnDeploymentPlanResult(
        stack_name="AWSAccelerator-InstallerStack",
        operation=operation,
        stack_status=stack_status,
        resolved_parameters={},
    )

    with pytest.raises(LzaError, match="unsafe or unknown"):
        validate_cloudformation_plan(plan)


def test_inspect_installer_source_codecommit_inaccessible_fails_closed() -> None:
    """Unexpected CodeCommit errors return INACCESSIBLE and fail deployment source preflight."""
    mock_cc = MagicMock()
    mock_cc.get_repository.return_value = {"repositoryMetadata": {}}
    mock_cc.get_branch.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "Not authorized"}}, "GetBranch"
    )

    mock_factory = MagicMock()
    mock_factory.get_client.return_value = mock_cc

    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test", slug="test"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0"),
    )
    config.installer.source_code.repository_type = "codecommit"
    config.installer.source_code.repository_name = "test-repo"
    config.installer.source_code.branch = "release/v1.16.0"

    with pytest.raises(LzaError, match="CodeCommit source is a manual prerequisite"):
        inspect_installer_source(
            factory=mock_factory,
            config=config,
            region="us-east-1",
        )

