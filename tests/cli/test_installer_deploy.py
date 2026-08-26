"""Tests for lza installer deploy CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from lza_workbench.aws.cloudformation import CfnDeploymentPlanResult, CfnStackStatusResult
from lza_workbench.aws.codecommit import CodeCommitRepositoryStatus
from lza_workbench.aws.context import AwsExecutionContext
from lza_workbench.cli import app
from lza_workbench.workflows.installer_deploy import (
    InstallerDeploymentPreparation,
    InstallerDeployResult,
)
from lza_workbench.workspace.config import load_workspace_config, write_workspace_config
from lza_workbench.workspace.schema import (
    AwsConfig,
    CustomerConfig,
    LzaConfig,
    WorkspaceConfig,
    WorkspaceState,
)
from lza_workbench.workspace.state import load_workspace_state, write_workspace_state


def test_cli_installer_deploy_missing_aws_profile_failure(
    tmp_path: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws_dir = tmp_path / "no-aws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    config = WorkspaceConfig(
        customer=CustomerConfig(name="No AWS", slug="no-aws"),
        aws=AwsConfig(profile="default", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0"),
    )
    write_workspace_config(ws_dir, config)

    # Blank out profile directly in yaml to trigger validation failure
    (ws_dir / "lza-workspace.yaml").write_text(
        "customer:\n  name: No AWS\n  slug: no-aws\naws:\n  profile: ''\n  region: us-east-1\n"
    )

    monkeypatch.chdir(ws_dir)
    result = cli_runner.invoke(app, ["installer", "deploy"])
    assert result.exit_code == 1


def test_cli_installer_deploy_missing_required_params_failure(
    tmp_path: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws_dir = tmp_path / "incomplete"
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / "aws-accelerator-config").mkdir(parents=True, exist_ok=True)
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Incomplete", slug="incomplete"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0"),
    )
    write_workspace_config(ws_dir, config)

    monkeypatch.chdir(ws_dir)
    result = cli_runner.invoke(app, ["installer", "deploy"])
    assert result.exit_code == 1
    assert "missing required installer configuration" in (result.output or str(result.exception))


def test_cli_installer_deploy_refuses_imported_workspace(
    tmp_path: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws_dir = tmp_path / "imported-ws-deploy"
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / ".lza").mkdir(parents=True, exist_ok=True)
    (ws_dir / "aws-accelerator-config").mkdir(parents=True, exist_ok=True)

    config = WorkspaceConfig(
        customer=CustomerConfig(name="Imported Customer", slug="imported-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0"),
    )
    write_workspace_config(ws_dir, config)
    write_workspace_state(ws_dir, WorkspaceState.from_config(config))

    monkeypatch.chdir(ws_dir)
    result = cli_runner.invoke(app, ["installer", "deploy"])
    assert result.exit_code == 1
    assert "missing required installer configuration" in (result.output or str(result.exception))


@patch("lza_workbench.workflows.installer_deploy.resolve_aws_execution_context")
@patch("lza_workbench.workflows.installer_deploy.inspect_cloudformation_stack")
def test_cli_installer_deploy_dry_run(
    mock_inspect_cfn: MagicMock,
    mock_resolve_context: MagicMock,
    configured_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    monkeypatch.chdir(configured_workspace)
    result = cli_runner.invoke(app, ["installer", "deploy", "--dry-run", "--force"])

    assert result.exit_code == 0
    assert "Dry run" in result.output
    state = load_workspace_state(configured_workspace)
    assert state.installer_stack_id is None


@patch("lza_workbench.workflows.installer_deploy.stream_cloudformation_stack_events")
@patch("lza_workbench.workflows.installer_deploy.deploy_cloudformation_stack")
@patch("lza_workbench.workflows.installer_deploy.inspect_cloudformation_stack")
@patch("lza_workbench.installer.deployment.inspect_codecommit_repository")
@patch("lza_workbench.workflows.installer_deploy.resolve_aws_execution_context")
def test_cli_installer_deploy_success(
    mock_resolve_context: MagicMock,
    mock_inspect_cc: MagicMock,
    mock_inspect_cfn: MagicMock,
    mock_deploy_cfn: MagicMock,
    mock_stream_cfn: MagicMock,
    configured_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    mock_inspect_cc.return_value = CodeCommitRepositoryStatus(
        repository_name="aws-accelerator-codecommit",
        branch_name="release/v1.16.0",
        exists=True,
        accessible=True,
        branch_exists=True,
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

    monkeypatch.chdir(configured_workspace)
    result = cli_runner.invoke(app, ["installer", "deploy", "--force"])

    assert result.exit_code == 0
    state = load_workspace_state(configured_workspace)
    assert state.installer_stack_status == "CREATE_COMPLETE"
    assert (
        state.installer_stack_id
        == "arn:aws:cloudformation:us-east-1:123456789012:stack/AWSAccelerator-InstallerStack/uuid"
    )
    assert state.management_account_id == "123456789012"


def test_cli_installer_deploy_missing_assets_bucket_failure(
    configured_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_workspace_config(configured_workspace)
    config.assets_bucket = None
    write_workspace_config(configured_workspace, config)

    monkeypatch.chdir(configured_workspace)
    result = cli_runner.invoke(app, ["installer", "deploy"])
    assert result.exit_code == 1
    assert "Workbench assets bucket is not configured" in (result.output or str(result.exception))


@patch("lza_workbench.cli.commands.installer_deploy.apply_installer_deployment")
@patch("lza_workbench.cli.commands.installer_deploy.prepare_installer_deployment")
def test_cli_installer_deploy_reuses_prepared_deployment(
    mock_prepare: MagicMock,
    mock_apply: MagicMock,
    configured_workspace: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_workspace_config(configured_workspace)
    preparation = InstallerDeploymentPreparation(
        workspace_dir=configured_workspace,
        config=config,
        aws_context=AwsExecutionContext(
            region="us-east-1",
            factory=MagicMock(),
            identity={"account": "123456789012", "arn": "arn:aws:iam::123:user/test"},
            error=None,
        ),
        template_path=configured_workspace / "template.json",
        template_digest="digest",
        resolved_parameters={},
        stack_name="AWSAccelerator-InstallerStack",
        operation="CREATE",
        cfn_plan=CfnDeploymentPlanResult(
            stack_name="AWSAccelerator-InstallerStack",
            operation="CREATE",
            stack_status=None,
            resolved_parameters={},
        ),
        profile="test",
        account_id="123456789012",
    )
    mock_prepare.return_value = preparation
    mock_apply.return_value = InstallerDeployResult(
        workspace_dir=configured_workspace,
        stack_name=preparation.stack_name,
        operation="CREATE",
        cfn_plan=preparation.cfn_plan,
        stack_id="stack-id",
        final_status=CfnStackStatusResult(
            stack_name=preparation.stack_name,
            exists=True,
            stack_status="CREATE_COMPLETE",
        ),
        dry_run=False,
        skipped=False,
    )

    monkeypatch.chdir(configured_workspace)
    result = cli_runner.invoke(app, ["installer", "deploy", "--force"])

    assert result.exit_code == 0
    mock_prepare.assert_called_once_with(target_dir=None, dry_run=False)
    mock_apply.assert_called_once()
    assert mock_apply.call_args.kwargs["preparation"] is preparation
