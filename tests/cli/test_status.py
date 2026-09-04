"""Tests for the status CLI command suite (lza status, installer, config, pipeline)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from lza_workbench.aws.cloudformation import CfnStackStatusResult
from lza_workbench.aws.context import AwsExecutionContext
from lza_workbench.cli import app
from lza_workbench.cli.commands.status_config import (
    status_config_command as run_config_status,
)
from lza_workbench.cli.commands.status_root import (
    status_root_command as run_root_status,
)
from lza_workbench.workspace.schema import (
    AwsConfig,
    CustomerConfig,
    WorkspaceConfig,
    WorkspaceState,
)

runner = CliRunner()


def test_status_pipeline_command_is_completely_removed() -> None:
    """Verify lza status pipeline is not registered and returns a non-zero exit code."""
    result = runner.invoke(app, ["status", "pipeline"])
    assert result.exit_code != 0
    assert "No such command 'pipeline'" in result.output or "Error" in result.output


@patch("lza_workbench.workflows.status_root.get_cloudformation_stack_status")
@patch("lza_workbench.workflows.status_root.resolve_aws_execution_context")
def test_run_root_status(
    mock_resolve_context: MagicMock,
    mock_get_cfn: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lza-workspace.yaml").write_text(
        "customer:\n  name: Test\n  slug: test\naws:\n  profile: default\n  region: us-east-1\n"
    )
    mock_factory = MagicMock()
    mock_resolve_context.return_value = AwsExecutionContext(
        region="us-east-1",
        factory=mock_factory,
        identity={"account": "123456789012", "arn": "arn:aws:iam::123:user/test"},
        error=None,
    )
    mock_get_cfn.return_value = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack", exists=True, stack_status="CREATE_COMPLETE"
    )

    run_root_status(target_dir=tmp_path)


@patch("lza_workbench.workflows.status_config.load_workspace_context")
def test_run_config_status(mock_load_ctx: MagicMock, tmp_path: Path) -> None:
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
    )
    state = WorkspaceState()
    mock_ctx = MagicMock()
    mock_ctx.workspace_dir = tmp_path
    mock_ctx.config = config
    mock_ctx.state = state
    mock_load_ctx.return_value = mock_ctx

    run_config_status(target_dir=tmp_path)


@patch("lza_workbench.workflows.status_config.load_workspace_context")
def test_run_config_status_renders_failed_pipeline_stage_and_action(
    mock_load_ctx: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
    )
    state = WorkspaceState(
        config_pipeline_status="Failed",
        config_pipeline_failed_stage="BuildStage",
        config_pipeline_failed_action="SynthAction",
        config_pipeline_error="CFN Stack synthesis error",
    )
    mock_ctx = MagicMock()
    mock_ctx.workspace_dir = tmp_path
    mock_ctx.config = config
    mock_ctx.state = state
    mock_load_ctx.return_value = mock_ctx

    run_config_status(target_dir=tmp_path)
    captured = capsys.readouterr().out
    assert "BuildStage" in captured
    assert "SynthAction" in captured
    assert "CFN Stack synthesis error" in captured



@patch("lza_workbench.workflows.status_installer.get_cloudformation_stack_status")
@patch("lza_workbench.workflows.status_installer.resolve_aws_execution_context")
@patch("lza_workbench.workflows.status_root.resolve_aws_execution_context")
def test_cli_status_commands(
    mock_main_context: MagicMock,
    mock_installer_context: MagicMock,
    mock_get_cfn: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lza-workspace.yaml").write_text(
        "customer:\n  name: Test\n  slug: test\naws:\n  profile: default\n  region: us-east-1\n"
    )
    mock_factory = MagicMock()
    aws_context = AwsExecutionContext(
        region="us-east-1",
        factory=mock_factory,
        identity={"account": "123456789012", "arn": "arn:aws:iam::123:user/test"},
        error=None,
    )
    mock_main_context.return_value = aws_context
    mock_installer_context.return_value = aws_context
    mock_get_cfn.return_value = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack", exists=True, stack_status="CREATE_COMPLETE"
    )

    res_root = runner.invoke(app, ["status"])
    assert res_root.exit_code == 0

    res_installer = runner.invoke(app, ["status", "installer"])
    assert res_installer.exit_code == 0
    assert "Config Pipeline Name" not in res_installer.output
    assert "Config Pipeline ARN" not in res_installer.output
    assert "Stack Outputs" not in res_installer.output
    assert "No stack outputs available" not in res_installer.output
    assert "Pipeline Status" in res_installer.output

    # Test lza installer status alias
    res_installer_alias = runner.invoke(app, ["installer", "status"])
    assert res_installer_alias.exit_code == 0
    assert "Config Pipeline Name" not in res_installer_alias.output
    assert "Config Pipeline ARN" not in res_installer_alias.output
    assert "Stack Outputs" not in res_installer_alias.output
    assert "No stack outputs available" not in res_installer_alias.output
    assert "Pipeline Status" in res_installer_alias.output

    res_config = runner.invoke(app, ["status", "config"])
    assert res_config.exit_code == 0
    assert "LZA Configuration Status - Test" in res_config.output
    assert "Local Configuration" in res_config.output
    assert "Repository Settings" in res_config.output

    # Test lza config status alias
    res_config_alias = runner.invoke(app, ["config", "status"])
    assert res_config_alias.exit_code == 0
    assert "LZA Configuration Status - Test" in res_config_alias.output
    assert "Local Configuration" in res_config_alias.output
    assert "Repository Settings" in res_config_alias.output



@patch("lza_workbench.workflows.status_installer.get_cloudformation_stack_status")
@patch("lza_workbench.workflows.status_config.resolve_aws_execution_context")
@patch("lza_workbench.workflows.status_root.resolve_aws_execution_context")
def test_cli_status_config_s3_bucket_derived(
    mock_root_context: MagicMock,
    mock_config_context: MagicMock,
    mock_get_cfn: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lza-workspace.yaml").write_text(
        "customer:\n  name: Test\n  slug: test\n"
        "aws:\n  profile: default\n  region: us-east-1\n"
        "configuration:\n  repository:\n    type: s3\n"
    )
    mock_factory = MagicMock()
    s3_mock = MagicMock()
    s3_mock.head_bucket.return_value = {}
    s3_mock.get_bucket_versioning.return_value = {"Status": "Enabled"}
    s3_mock.get_bucket_encryption.return_value = {
        "ServerSideEncryptionConfiguration": {
            "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "aws:kms"}}]
        }
    }
    s3_mock.head_object.return_value = {
        "ETag": '"test-etag-123"',
        "VersionId": "v1",
        "ContentLength": 1024,
        "LastModified": datetime(2026, 8, 26, 10, 0, 0, tzinfo=UTC),
    }

    mock_factory.get_client.return_value = s3_mock
    aws_context = AwsExecutionContext(
        region="us-east-1",
        factory=mock_factory,
        identity={"account": "123456789012", "arn": "arn:aws:iam::123:user/test"},
        error=None,
    )
    mock_root_context.return_value = aws_context
    mock_config_context.return_value = aws_context
    mock_get_cfn.return_value = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack", exists=False
    )

    res_config = runner.invoke(app, ["status", "config"])
    assert res_config.exit_code == 0
    assert "aws-accelerator-config-123456789012-us-east-1" in res_config.output
    assert "S3 Bucket: Not set" not in res_config.output

    res_root = runner.invoke(app, ["status"])
    assert res_root.exit_code == 0
    assert "aws-accelerator-config-123456789012-us-east-1" in res_root.output
    assert "S3 Target: Not set" not in res_root.output


@patch("lza_workbench.workflows.status_root.get_pipeline_execution")
@patch("lza_workbench.workflows.status_root.get_pipeline_state")
@patch("lza_workbench.workflows.status_root.get_cloudformation_stack_status")
@patch("lza_workbench.workflows.status_root.resolve_aws_execution_context")
def test_cli_status_live_success_summary(
    mock_root_context: MagicMock,
    mock_get_cfn: MagicMock,
    mock_get_pipe_state: MagicMock,
    mock_get_pipe_exec: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lza-workspace.yaml").write_text(
        "customer:\n  name: Acme Corp\n  slug: acme\n"
        "aws:\n  profile: acme-root\n  region: us-east-1\n"
        "configuration:\n  repository:\n    type: codecommit\n    repository_name: acme-config\n"
    )
    mock_factory = MagicMock()
    mock_root_context.return_value = AwsExecutionContext(
        region="us-east-1",
        factory=mock_factory,
        identity={"account": "123456789012", "arn": "arn:aws:iam::123:user/test"},
        error=None,
    )
    mock_get_cfn.return_value = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack",
        exists=True,
        stack_status="UPDATE_COMPLETE",
        deployed_parameters={"RepositoryBranchName": "release/v1.16.0"},
    )
    mock_get_pipe_state.side_effect = [
        MagicMock(
            exists=True,
            status="Succeeded",
            latest_execution_id="inst-exec-123",
            stage_states=[],
        ),
        MagicMock(
            exists=True,
            status="Succeeded",
            latest_execution_id="cfg-exec-456",
            stage_states=[],
        ),
    ]
    mock_get_pipe_exec.side_effect = [
        MagicMock(start_time="2026-09-01T12:00:00Z", duration_seconds=185.0),
        MagicMock(start_time="2026-09-01T12:05:00Z", duration_seconds=92.0),
    ]

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    out = result.output

    assert "1. Installer" in out
    assert "Stack Name: AWSAccelerator-InstallerStack" in out
    assert "Update Complete" in out
    assert "Deployed Version: v1.16.0" in out
    assert "Installer Pipeline: AWSAccelerator-Installer" in out
    assert "inst-exec-123" in out
    assert "3m 5s" in out

    assert "2. Configuration" in out
    assert "codecommit / acme-config" in out
    assert "Configuration Pipeline: AWSAccelerator-Pipeline" in out
    assert "cfg-exec-456" in out
    assert "1m 32s" in out

    assert "3. Overall Status" in out
    assert "Installer: Healthy" in out
    assert "Configuration: Healthy" in out
    assert "Workspace: Healthy" in out
    assert "lza status pipeline" not in out


@patch("lza_workbench.workflows.status_root.collect_pipeline_action_failures")
@patch("lza_workbench.workflows.status_root.get_pipeline_execution")
@patch("lza_workbench.workflows.status_root.get_pipeline_state")
@patch("lza_workbench.workflows.status_root.get_cloudformation_stack_status")
@patch("lza_workbench.workflows.status_root.resolve_aws_execution_context")
def test_cli_status_installer_pipeline_failed(
    mock_root_context: MagicMock,
    mock_get_cfn: MagicMock,
    mock_get_pipe_state: MagicMock,
    mock_get_pipe_exec: MagicMock,
    mock_failures: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lza-workspace.yaml").write_text(
        "customer:\n  name: Acme Corp\n  slug: acme\n"
        "aws:\n  profile: acme-root\n  region: us-east-1\n"
    )
    mock_root_context.return_value = AwsExecutionContext(
        region="us-east-1",
        factory=MagicMock(),
        identity={"account": "123456789012", "arn": "arn:aws:iam::123:user/test"},
        error=None,
    )
    mock_get_cfn.return_value = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack",
        exists=True,
        stack_status="UPDATE_COMPLETE",
        deployed_parameters={"RepositoryBranchName": "release/v1.16.0"},
    )
    mock_get_pipe_state.side_effect = [
        MagicMock(
            exists=True,
            status="Failed",
            latest_execution_id="inst-exec-fail",
            stage_states=[MagicMock()],
        ),
        MagicMock(
            exists=True,
            status="Succeeded",
            latest_execution_id="cfg-exec-ok",
            stage_states=[],
        ),
    ]
    mock_get_pipe_exec.return_value = MagicMock(
        start_time="2026-09-01T12:00:00Z", duration_seconds=60.0
    )
    mock_failures.return_value = [
        MagicMock(
            stage_name="DeployStage",
            action_name="CfnAction",
            diagnostic_details=["CloudFormation deployment failed: resource limit reached"],
            error_message=None,
            summary=None,
        )
    ]

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    out = result.output

    assert "Failed Stage: DeployStage" in out
    assert "Failed Action: CfnAction" in out
    assert "CloudFormation deployment failed: resource limit reached" in out
    assert "Installer: Failed" in out
    assert "Workspace: Attention Required" in out


@patch("lza_workbench.workflows.status_root.collect_pipeline_action_failures")
@patch("lza_workbench.workflows.status_root.get_pipeline_execution")
@patch("lza_workbench.workflows.status_root.get_pipeline_state")
@patch("lza_workbench.workflows.status_root.get_cloudformation_stack_status")
@patch("lza_workbench.workflows.status_root.resolve_aws_execution_context")
def test_cli_status_config_pipeline_failed(
    mock_root_context: MagicMock,
    mock_get_cfn: MagicMock,
    mock_get_pipe_state: MagicMock,
    mock_get_pipe_exec: MagicMock,
    mock_failures: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lza-workspace.yaml").write_text(
        "customer:\n  name: Acme Corp\n  slug: acme\n"
        "aws:\n  profile: acme-root\n  region: us-east-1\n"
    )
    mock_root_context.return_value = AwsExecutionContext(
        region="us-east-1",
        factory=MagicMock(),
        identity={"account": "123456789012", "arn": "arn:aws:iam::123:user/test"},
        error=None,
    )
    mock_get_cfn.return_value = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack",
        exists=True,
        stack_status="UPDATE_COMPLETE",
        deployed_parameters={"RepositoryBranchName": "release/v1.16.0"},
    )
    mock_get_pipe_state.side_effect = [
        MagicMock(
            exists=True,
            status="Succeeded",
            latest_execution_id="inst-exec-ok",
            stage_states=[],
        ),
        MagicMock(
            exists=True,
            status="Failed",
            latest_execution_id="cfg-exec-fail",
            stage_states=[MagicMock()],
        ),
    ]
    mock_get_pipe_exec.return_value = MagicMock(
        start_time="2026-09-01T12:00:00Z", duration_seconds=45.0
    )
    mock_failures.return_value = [
        MagicMock(
            stage_name="BuildStage",
            action_name="SynthAction",
            diagnostic_details=["CDK synth failed: missing required variable"],
            error_message=None,
            summary=None,
        )
    ]

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    out = result.output

    assert "Failed Stage: BuildStage" in out
    assert "Failed Action: SynthAction" in out
    assert "CDK synth failed: missing required variable" in out
    assert "Configuration: Failed" in out
    assert "Workspace: Attention Required" in out


@patch("lza_workbench.workflows.status_root.get_pipeline_execution")
@patch("lza_workbench.workflows.status_root.get_pipeline_state")
@patch("lza_workbench.workflows.status_root.get_cloudformation_stack_status")
@patch("lza_workbench.workflows.status_root.resolve_aws_execution_context")
def test_cli_status_active_pipeline_execution(
    mock_root_context: MagicMock,
    mock_get_cfn: MagicMock,
    mock_get_pipe_state: MagicMock,
    mock_get_pipe_exec: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lza-workspace.yaml").write_text(
        "customer:\n  name: Acme Corp\n  slug: acme\n"
        "aws:\n  profile: acme-root\n  region: us-east-1\n"
    )
    mock_root_context.return_value = AwsExecutionContext(
        region="us-east-1",
        factory=MagicMock(),
        identity={"account": "123456789012", "arn": "arn:aws:iam::123:user/test"},
        error=None,
    )
    mock_get_cfn.return_value = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack",
        exists=True,
        stack_status="UPDATE_COMPLETE",
        deployed_parameters={"RepositoryBranchName": "release/v1.16.0"},
    )
    stage_mock = MagicMock(
        stage_name="SynthesizeStage",
        status="InProgress",
        actions=[MagicMock(action_name="SynthAction", status="InProgress")],
    )
    mock_get_pipe_state.side_effect = [
        MagicMock(
            exists=True,
            status="Succeeded",
            latest_execution_id="inst-exec-ok",
            stage_states=[],
        ),
        MagicMock(
            exists=True,
            status="InProgress",
            latest_execution_id="cfg-exec-running",
            stage_states=[stage_mock],
        ),
    ]
    mock_get_pipe_exec.return_value = MagicMock(
        start_time="2026-09-01T12:00:00Z", duration_seconds=30.0
    )

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    out = result.output

    assert "Current Stage/Action: SynthesizeStage / SynthAction" in out
    assert "Configuration: Running" in out
    assert "Workspace: Running" in out


@patch("lza_workbench.workflows.status_root.get_pipeline_state")
@patch("lza_workbench.workflows.status_root.get_cloudformation_stack_status")
@patch("lza_workbench.workflows.status_root.resolve_aws_execution_context")
def test_cli_status_missing_pipeline(
    mock_root_context: MagicMock,
    mock_get_cfn: MagicMock,
    mock_get_pipe_state: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lza-workspace.yaml").write_text(
        "customer:\n  name: Acme Corp\n  slug: acme\n"
        "aws:\n  profile: acme-root\n  region: us-east-1\n"
    )
    mock_root_context.return_value = AwsExecutionContext(
        region="us-east-1",
        factory=MagicMock(),
        identity={"account": "123456789012", "arn": "arn:aws:iam::123:user/test"},
        error=None,
    )
    mock_get_cfn.return_value = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack", exists=False
    )
    mock_get_pipe_state.side_effect = [
        MagicMock(exists=False, status="NOT_DEPLOYED"),
        MagicMock(exists=False, status="NOT_DEPLOYED"),
    ]

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    out = result.output

    assert "Not Deployed" in out
    assert "Installer: Incomplete" in out
    assert "Configuration: Incomplete" in out
    assert "Workspace: Incomplete" in out


@patch("lza_workbench.workflows.status_root.resolve_aws_execution_context")
def test_cli_status_aws_unavailable_state_fallback(
    mock_root_context: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lza-workspace.yaml").write_text(
        "customer:\n  name: Acme Corp\n  slug: acme\n"
        "aws:\n  profile: comm-it-root\n  region: us-east-1\n"
    )
    lza_dir = tmp_path / ".lza"
    lza_dir.mkdir(parents=True, exist_ok=True)
    (lza_dir / "state.json").write_text(
        '{\n'
        '  "installer_stack_status": "UPDATE_COMPLETE",\n'
        '  "installer_template_version": "v1.16.0",\n'
        '  "installer_pipeline_status": "Succeeded",\n'
        '  "installer_pipeline_execution_id": "exec-inst-rec",\n'
        '  "config_pipeline_status": "Failed",\n'
        '  "config_pipeline_execution_id": "exec-cfg-rec",\n'
        '  "config_pipeline_failed_stage": "DeployStage",\n'
        '  "config_pipeline_failed_action": "RunDeploy",\n'
        '  "config_pipeline_error": "CDK Deploy Failed"\n'
        '}'
    )
    mock_root_context.return_value = AwsExecutionContext(
        region="us-east-1",
        factory=MagicMock(),
        identity=None,
        error="AWS authentication validation failed for 'comm-it-root': SSO session invalid",
    )

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    out = result.output

    assert "AWS Access Notice: AWS authentication validation failed for 'comm-it-root'" in out
    assert "(Recorded)" in out
    assert "Update Complete (Recorded)" in out
    assert "v1.16.0 (Recorded)" in out
    assert "Succeeded (Recorded)" in out
    assert "Failed (Recorded)" in out
    assert "DeployStage (Recorded)" in out
    assert "CDK Deploy Failed" in out
    assert "Workspace: AWS Unavailable - Showing Last Known State" in out
    assert "Workspace: Healthy" not in out


@patch("lza_workbench.workflows.status_root.resolve_aws_execution_context")
def test_cli_status_aws_unavailable_no_state(
    mock_root_context: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lza-workspace.yaml").write_text(
        "customer:\n  name: Acme Corp\n  slug: acme\n"
        "aws:\n  profile: comm-it-root\n  region: us-east-1\n"
    )
    mock_root_context.return_value = AwsExecutionContext(
        region="us-east-1",
        factory=MagicMock(),
        identity=None,
        error="No credentials found",
    )

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    out = result.output

    assert "AWS Access Notice: No credentials found" in out
    assert "Workspace: AWS Unavailable - No Recorded State" in out
    assert "Workspace: Healthy" not in out


