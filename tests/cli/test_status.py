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
from lza_workbench.cli.commands.status_pipeline import (
    status_pipeline_command as run_pipeline_status,
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


def test_pipeline_status_displays_separate_execution_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
    )
    state = WorkspaceState(
        installer_pipeline_execution_id="installer-execution",
        config_pipeline_execution_id="config-execution",
    )
    mock_ctx = MagicMock(workspace_dir=tmp_path, config=config, state=state)
    aws_context = AwsExecutionContext(
        region="us-east-1", factory=MagicMock(), identity=None, error="No credentials"
    )
    monkeypatch.setattr(
        "lza_workbench.workflows.status_pipeline.load_workspace_context",
        lambda *_args, **_kwargs: mock_ctx,
    )
    monkeypatch.setattr(
        "lza_workbench.workflows.status_pipeline.resolve_aws_execution_context",
        lambda *args, **kwargs: aws_context,
    )

    result = runner.invoke(app, ["status", "pipeline"])

    assert result.exit_code == 0
    assert "installer-execution" in result.output
    assert "config-execution" in result.output


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



@patch("lza_workbench.workflows.status_pipeline.resolve_aws_execution_context")
def test_run_pipeline_status(
    mock_resolve_context: MagicMock,
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

    run_pipeline_status(target_dir=tmp_path)


@patch("lza_workbench.workflows.status_installer.get_cloudformation_stack_status")
@patch("lza_workbench.workflows.status_installer.resolve_aws_execution_context")
@patch("lza_workbench.workflows.status_root.resolve_aws_execution_context")
@patch("lza_workbench.workflows.status_pipeline.resolve_aws_execution_context")
def test_cli_status_commands(
    mock_pipeline_context: MagicMock,
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
    mock_pipeline_context.return_value = aws_context
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

    res_pipeline = runner.invoke(app, ["status", "pipeline"])
    assert res_pipeline.exit_code == 0
    assert "LZA Pipeline Status - Test" in res_pipeline.output
    assert "1. Installer Pipeline" in res_pipeline.output
    assert "2. Configuration Pipeline" in res_pipeline.output
    assert "3. Execution History" in res_pipeline.output



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


