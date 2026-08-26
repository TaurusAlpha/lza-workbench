"""Tests for status workflows and status synchronization."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lza_workbench.aws.cloudformation import CfnStackStatusResult
from lza_workbench.errors import LzaError
from lza_workbench.workflows.status_config import (
    ConfigurationStatusResult,
    get_config_status_workflow,
)
from lza_workbench.workflows.status_installer import (
    InstallerStatusResult,
    get_installer_status_workflow,
    prepare_installer_status,
    sync_installer_config,
    sync_installer_state,
)
from lza_workbench.workflows.status_pipeline import (
    PipelineStatusResult,
    get_pipeline_status_workflow,
)
from lza_workbench.workflows.status_root import (
    RootStatusResult,
    get_root_status_workflow,
)
from lza_workbench.workspace.config import load_workspace_config
from lza_workbench.workspace.schema import (
    AwsConfig,
    CustomerConfig,
    WorkspaceConfig,
    WorkspaceState,
)
from lza_workbench.workspace.state import load_workspace_state


def test_get_root_status_workflow(configured_workspace: Path) -> None:
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        mock_client.return_value = MagicMock()
        result = get_root_status_workflow(target_dir=configured_workspace)
        assert isinstance(result, RootStatusResult)
        assert result.customer_name == "Acme Corp"
        assert result.profile == "acme-root"
        assert result.region == "eu-west-1"


def test_get_config_status_workflow(configured_workspace: Path) -> None:
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
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
            "LastModified": "2026-08-26T10:00:00Z",
        }
        pipe_mock = MagicMock()
        pipe_mock.get_pipeline_state.return_value = {
            "stageStates": [
                {
                    "stageName": "Source",
                    "latestExecution": {
                        "status": "Succeeded",
                        "pipelineExecutionId": "exec-1",
                    },
                    "actionStates": [
                        {
                            "actionName": "SourceAction",
                            "latestExecution": {"status": "Succeeded"},
                        }
                    ],
                }
            ]
        }

        def client_side_effect(service_name: str, **_kwargs):
            if service_name == "s3":
                return s3_mock
            if service_name == "codepipeline":
                return pipe_mock
            return MagicMock()

        mock_client.side_effect = client_side_effect

        result = get_config_status_workflow(target_dir=configured_workspace)
        assert isinstance(result, ConfigurationStatusResult)
        assert result.customer_name == "Acme Corp"
        assert result.config_dir_exists is True
        assert result.repository_type == "s3"
        assert result.s3_bucket_exists is True
        assert result.s3_bucket_versioning is True
        assert result.s3_bucket_encryption is True
        assert result.s3_object_exists is True
        assert result.s3_object_etag == "test-etag-123"
        assert result.pipeline_state is not None
        assert result.pipeline_state.status == "Succeeded"


def test_get_config_status_workflow_codecommit(tmp_path: Path) -> None:
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
    )
    config.configuration.repository.type = "codecommit"
    config.configuration.repository.repository_name = "test-config-repo"
    config.configuration.repository.branch = "main"

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
        patch(
            "lza_workbench.workflows.status_config.inspect_codecommit_config_repository"
        ) as mock_cc,
        patch("lza_workbench.workflows.status_config.get_pipeline_state") as mock_pipe,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        mock_client.return_value = MagicMock()
        mock_cc.return_value = {
            "exists": True,
            "accessible": True,
            "branch_exists": True,
            "error": None,
        }
        mock_pipe.return_value = MagicMock(
            pipeline_name="AWSAccelerator-Pipeline", exists=True, status="Succeeded"
        )

        result = get_config_status_workflow(
            config=config,
            state=WorkspaceState(),
            workspace_dir=tmp_path,
        )
        assert result.repository_type == "codecommit"
        assert result.codecommit_exists is True
        assert result.codecommit_branch_exists is True
        assert result.codecommit_accessible is True


def test_get_config_status_workflow_codeconnection(tmp_path: Path) -> None:
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
    )
    config.configuration.repository.type = "codeconnection"
    config.configuration.repository.codeconnection_arn = (
        "arn:aws:codeconnections:us-east-1:123456789012:connection/test-id"
    )
    config.configuration.repository.owner = "my-org"
    config.configuration.repository.repository_name = "my-repo"

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
        patch("lza_workbench.workflows.status_config.inspect_codeconnection") as mock_conn,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        mock_client.return_value = MagicMock()
        mock_conn.return_value = MagicMock(
            arn="arn:aws:codeconnections:us-east-1:123456789012:connection/test-id",
            status="AVAILABLE",
            provider_type="GitHub",
            owner_account_id="123456789012",
            error=None,
        )

        result = get_config_status_workflow(
            config=config,
            state=WorkspaceState(),
            workspace_dir=tmp_path,
        )
        assert result.repository_type == "codeconnection"
        assert result.codeconnection_status == "AVAILABLE"
        assert result.codeconnection_provider == "GitHub"


def test_git_working_tree_and_remote_sync_helpers(tmp_path: Path) -> None:
    from lza_workbench.configuration.git import (
        _run_git_command,
        get_git_remote_sync_status,
        get_git_working_tree_status,
        init_git_repository,
    )

    # Empty directory
    assert get_git_working_tree_status(tmp_path) is None

    # Init git repo
    init_git_repository(tmp_path)
    status1 = get_git_working_tree_status(tmp_path)
    assert status1 is not None
    assert status1.is_git is True
    assert status1.has_uncommitted is False

    # Add file without commit
    (tmp_path / "test.txt").write_text("hello")
    status2 = get_git_working_tree_status(tmp_path)
    assert status2 is not None
    assert status2.has_uncommitted is True
    assert status2.uncommitted_count == 1

    # Commit file
    _run_git_command(["add", "test.txt"], cwd=tmp_path)
    _run_git_command(
        [
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-m",
            "Initial commit",
        ],
        cwd=tmp_path,
    )

    status3 = get_git_working_tree_status(tmp_path)
    assert status3 is not None
    assert status3.has_uncommitted is False
    assert status3.commit_subject == "Initial commit"

    # Remote sync status without remote
    sync = get_git_remote_sync_status(tmp_path)
    assert sync.status == "No Upstream"




def test_get_pipeline_status_workflow(configured_workspace: Path) -> None:
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        mock_client.return_value = MagicMock()
        result = get_pipeline_status_workflow(target_dir=configured_workspace)
        assert isinstance(result, PipelineStatusResult)
        assert result.installer_pipeline_name == "AWSAccelerator-Installer"
        assert result.config_pipeline_name == "AWSAccelerator-Pipeline"


def test_get_installer_status_workflow(configured_workspace: Path) -> None:
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
        patch(
            "lza_workbench.workflows.status_installer.get_cloudformation_stack_status"
        ) as mock_st,
        patch("lza_workbench.workflows.status_installer.get_pipeline_state") as mock_pipe,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        mock_client.return_value = MagicMock()
        mock_st.return_value = CfnStackStatusResult(
            stack_name="AWSAccelerator-InstallerStack",
            exists=True,
            stack_status="CREATE_COMPLETE",
            stack_id="arn:aws:cloudformation:stack/123",
            deployed_parameters={"RepositoryBranchName": "release/v1.16.0"},
            outputs={"OutputKey": "OutputVal"},
        )
        mock_pipe.return_value = MagicMock(
            pipeline_name="AWSAccelerator-Installer", exists=True, status="Succeeded"
        )
        result = get_installer_status_workflow(target_dir=configured_workspace)
        assert isinstance(result, InstallerStatusResult)
        assert result.cfn_status.exists is True
        assert result.deployed_version == "v1.16.0"
        assert result.pipeline_state is not None
        assert result.pipeline_state.status == "Succeeded"


def test_sync_installer_state_raises_when_not_exists(tmp_path: Path) -> None:
    state = WorkspaceState()
    cfn_status = CfnStackStatusResult(stack_name="AWSAccelerator-InstallerStack", exists=False)
    with pytest.raises(LzaError, match="Cannot synchronize state"):
        sync_installer_state(
            workspace_dir=tmp_path,
            state=state,
            cfn_status=cfn_status,
            deployed_version="v1.15.5",
        )


def test_sync_installer_state_success(tmp_path: Path) -> None:
    state = WorkspaceState()
    cfn_status = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack",
        exists=True,
        stack_id="arn:aws:cloudformation:us-east-1:123:stack/test/123",
        stack_status="CREATE_COMPLETE",
    )
    new_state = sync_installer_state(
        workspace_dir=tmp_path,
        state=state,
        cfn_status=cfn_status,
        deployed_version="v1.15.5",
    )
    assert new_state.installer_stack_id == cfn_status.stack_id
    assert new_state.installer_stack_status == "CREATE_COMPLETE"
    assert new_state.installer_template_version == "v1.15.5"

    loaded_state = load_workspace_state(tmp_path)
    assert loaded_state.installer_stack_id == cfn_status.stack_id


def test_sync_installer_config_success(tmp_path: Path) -> None:
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
    )
    cfn_status = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack",
        exists=True,
        deployed_parameters={
            "RepositorySource": "codecommit",
            "RepositoryOwner": "aws",
            "RepositoryName": "aws-accelerator",
            "RepositoryBranchName": "release/v1.15.5",
            "ManagementAccountEmail": "mgmt@example.com",
            "EnableApprovalStage": "Yes",
        },
    )
    new_config = sync_installer_config(
        workspace_dir=tmp_path,
        config=config,
        cfn_status=cfn_status,
    )
    assert new_config.installer.source_code.repository_type == "codecommit"
    assert new_config.installer.options.management_account_email == "mgmt@example.com"
    assert new_config.installer.options.enable_approval_stage is True

    loaded_config = load_workspace_config(tmp_path)
    assert loaded_config.installer.options.management_account_email == "mgmt@example.com"


def test_sync_installer_config_accepts_codeconnection_repository(tmp_path: Path) -> None:
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
    )
    cfn_status = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack",
        exists=True,
        deployed_parameters={"ConfigurationRepositoryLocation": "codeconnection"},
    )

    new_config = sync_installer_config(
        workspace_dir=tmp_path,
        config=config,
        cfn_status=cfn_status,
    )

    assert new_config.configuration.repository.type == "codeconnection"


def test_prepare_installer_status_separates_comparisons_from_rendering(tmp_path: Path) -> None:
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
    )
    state = WorkspaceState(
        installer_stack_status="CREATE_COMPLETE",
        installer_template_version="v1.15.5",
    )
    cfn_status = CfnStackStatusResult(
        stack_name="AWSAccelerator-InstallerStack",
        exists=True,
        stack_status="CREATE_COMPLETE",
        deployed_parameters={"RepositoryBranchName": "release/v1.15.5"},
    )

    result = prepare_installer_status(
        workspace_dir=tmp_path,
        config=config,
        state=state,
        profile="test-profile",
        region="us-east-1",
        aws_identity=None,
        aws_error="No credentials",
        cfn_status=cfn_status,
    )

    assert result.deployed_version == "v1.15.5"
    assert result.state_alignment is not None
    assert result.state_alignment.in_sync is True


def test_get_config_status_uses_recorded_pipeline_state_without_aws_api(tmp_path: Path) -> None:
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
    )
    state = WorkspaceState(
        config_pipeline_execution_id="exec-456",
        config_pipeline_status="Failed",
        config_pipeline_failed_stage="Build",
        config_pipeline_failed_action="SynthesizeStack",
        config_pipeline_error="CodeBuild build failed with exit code 1",
    )

    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        # codepipeline client should NOT be queried when status is already in state
        result = get_config_status_workflow(
            config=config,
            state=state,
            workspace_dir=tmp_path,
        )
        assert result.pipeline_status == "Failed"
        assert result.pipeline_execution_id == "exec-456"
        assert result.pipeline_failed_stage == "Build"
        assert result.pipeline_failed_action == "SynthesizeStack"
        assert result.pipeline_error == "CodeBuild build failed with exit code 1"
        assert any("SynthesizeStack" in w for w in result.warnings)
        # Ensure get_client was not called with "codepipeline"
        for call_args in mock_client.call_args_list:
            assert call_args[0][0] != "codepipeline"


def test_get_config_status_extracts_codebuild_diagnostics_on_fallback(tmp_path: Path) -> None:
    from lza_workbench.aws.codepipeline import ActionStateResult, StageStateResult

    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
    )
    state = WorkspaceState()

    pipe_state = MagicMock(
        exists=True,
        status="Failed",
        latest_execution_id="exec-789",
        stage_states=[
            StageStateResult(
                stage_name="Build",
                status="Failed",
                actions=[
                    ActionStateResult(
                        action_name="Synth",
                        status="Failed",
                        summary="Action failed",
                        external_execution_id="build-id-123",
                        external_execution_url="https://console.aws.amazon.com/codebuild/...",
                    )
                ],
            )
        ],
    )


    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
        patch("lza_workbench.workflows.status_config.get_pipeline_state") as mock_get_pipe,
        patch("lza_workbench.workflows.status_config.fetch_codebuild_diagnostics") as mock_diag,
    ):
        mock_val.return_value = {"account": "123456789012", "arn": "arn:aws:iam::123:user/test"}
        mock_client.return_value = MagicMock()
        mock_get_pipe.return_value = pipe_state
        diag_msg = "❌ Stack AWSAccelerator-Network-Phase2 failed to deploy: ValidationError"
        mock_diag.return_value = [diag_msg]

        result = get_config_status_workflow(
            config=config,
            state=state,
            workspace_dir=tmp_path,
        )
        assert result.pipeline_status == "Failed"
        assert result.pipeline_failed_stage == "Build"
        assert result.pipeline_failed_action == "Synth"
        assert diag_msg in result.pipeline_error
        assert result.pipeline_failed_build_url == "https://console.aws.amazon.com/codebuild/..."



