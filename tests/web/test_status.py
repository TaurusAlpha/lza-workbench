"""Focused Web status API tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from lza_workbench.aws.cloudformation import (
    CfnDeploymentPlanResult,
    CfnStackStatusResult,
)
from lza_workbench.aws.codepipeline import PipelineStateResult
from lza_workbench.configuration.archive import ConfigDiffResult
from lza_workbench.configuration.git import GitRemoteSyncStatus, GitWorkingTreeStatus
from lza_workbench.configuration.status import (
    ConfigurationPipelineStatus,
    ConfigurationStatusResult,
    ConfigurationSynchronizationStatus,
    ConfigurationWorkspaceStatus,
    LocalGitStatus,
    S3ConfigurationRepositoryStatus,
)
from lza_workbench.configuration.sync import RemoteSyncStatus
from lza_workbench.errors import LzaError
from lza_workbench.installer.planning import InstallerPlanResult
from lza_workbench.installer.source import CodeCommitPlanResult
from lza_workbench.installer.status import StateAlignment
from lza_workbench.pipeline.failures import FailureCategory, FailureDiagnostic
from lza_workbench.pipeline.models import PipelineActionState, PipelineStageState
from lza_workbench.web.app import create_app
from lza_workbench.workflows.config_deploy import ConfigDeployResult
from lza_workbench.workflows.config_pull import ConfigPullPreparation, ConfigPullResult
from lza_workbench.workflows.config_push import ConfigPushPreparation, ConfigPushResult
from lza_workbench.workflows.installer_init import (
    InstallerForm,
    InstallerFormField,
    InstallerSettingsResult,
)
from lza_workbench.workflows.pipeline_snapshot import (
    PipelineActionFailure,
    PipelineSnapshotResult,
)
from lza_workbench.workflows.pipeline_start import PipelineStartResult
from lza_workbench.workflows.status_installer import InstallerStatusResult
from lza_workbench.workflows.status_root import (
    ConfigurationRepoSummary,
    InstallerStackSummary,
    OverallHealthSummary,
    PipelineSummary,
    RootStatusResult,
)
from lza_workbench.workflows.workspace_bootstrap import (
    BootstrapAction,
    BootstrapPlanResult,
    WorkspaceBootstrapResult,
)
from lza_workbench.workspace.schema import AwsConfig, CustomerConfig, WorkspaceConfig


def _config_status_result() -> ConfigurationStatusResult:
    now = datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC)
    return ConfigurationStatusResult(
        workspace=ConfigurationWorkspaceStatus(
            workspace_dir=Path("/workspaces/acme"),
            customer_name="Acme",
            lza_version="1.11.0",
            profile="acme-admin",
            region="eu-west-1",
            aws_identity={"account": "123456789012", "arn": "arn:aws:iam::123456789012:user/admin"},
            aws_error=None,
            config_dir=Path("/workspaces/acme/aws-accelerator-config"),
            config_dir_exists=True,
            yaml_files=("accounts-config.yaml", "global-config.yaml"),
            initialized_at=now,
            template_name="aws-best-practices",
            template_source=None,
            drifted_fields=(),
        ),
        local_git=LocalGitStatus(
            working_tree=GitWorkingTreeStatus(
                is_git=True,
                branch="main",
                commit="abc1234",
                commit_subject="Initial commit",
                has_uncommitted=False,
                uncommitted_count=0,
                remote_url="https://git-codecommit.eu-west-1.amazonaws.com/v1/repos/config",
                files_count=2,
            ),
            sync_status=GitRemoteSyncStatus(
                status="Synchronized",
                ahead=0,
                behind=0,
                summary="In Sync",
            ),
        ),
        repository=S3ConfigurationRepositoryStatus(
            bucket="acme-config-bucket",
            object_key="aws-accelerator-config.zip",
            bucket_exists=True,
            bucket_accessible=True,
            bucket_versioning=True,
            bucket_encryption=True,
            object_exists=True,
            object_etag="etag-xyz",
            object_version_id="ver-123",
            object_last_modified=now,
            object_size=45000,
            error=None,
        ),
        pipeline=ConfigurationPipelineStatus(
            name="AWSAccelerator-Pipeline",
            arn="arn:aws:codepipeline:eu-west-1:123456789012:AWSAccelerator-Pipeline",
            status="Succeeded",
            execution_id="exec-456",
            failed_stage=None,
            failed_action=None,
            failed_build_url=None,
            error=None,
            state=None,
        ),
        synchronization=ConfigurationSynchronizationStatus(
            has_state=True,
            recorded_pipeline_execution_id="exec-456",
            uploaded_at=now,
            downloaded_at=now,
            artifact_etag="etag-xyz",
            artifact_version_id="ver-123",
            remote_sync=RemoteSyncStatus(
                status="Synchronized",
                ahead=0,
                behind=0,
                summary="In Sync with S3 (ETag: etag-xyz)",
                is_synced=True,
            ),
        ),
        warnings=("Test warning message",),
    )


def _status_result() -> RootStatusResult:
    return RootStatusResult(
        workspace_dir=Path("/workspaces/acme"),
        customer_name="Acme",
        lza_version="1.11.0",
        profile="acme-admin",
        region="eu-west-1",
        aws_identity={"account": "123456789012", "arn": "arn:aws:iam::123456789012:user/admin"},
        aws_error=None,
        installer=InstallerStackSummary(
            name="AWSAccelerator-InstallerStack",
            status="CREATE_COMPLETE",
            exists=True,
            deployed_version="1.11.0",
        ),
        installer_pipeline=PipelineSummary(name="AWSAccelerator-Installer", status="Succeeded"),
        configuration_repo=ConfigurationRepoSummary(
            repository_type="s3",
            target="acme-config",
            remote_sync=RemoteSyncStatus(
                status="Synchronized",
                is_synced=True,
                summary="In Sync with S3 (ETag: 123)",
            ),
        ),
        configuration_pipeline=PipelineSummary(name="AWSAccelerator-Pipeline", status="Succeeded"),
        health=OverallHealthSummary(
            installer="Healthy",
            configuration="Healthy",
            workspace="Healthy",
        ),
    )


def test_status_api_serializes_root_status() -> None:
    app = create_app(workspace_dir=Path("/workspaces/acme"))
    with patch("lza_workbench.web.status.get_root_status_workflow", return_value=_status_result()):
        response = TestClient(app).get("/api/status")

    assert response.status_code == 200
    assert response.json()["workspace"] == {
        "directory": "/workspaces/acme",
        "customerName": "Acme",
        "lzaVersion": "1.11.0",
    }
    assert response.json()["installerPipeline"]["status"] == "Succeeded"
    assert response.json()["configuration"]["remoteSync"] == {
        "status": "Synchronized",
        "ahead": 0,
        "behind": 0,
        "summary": "In Sync with S3 (ETag: 123)",
        "isSynced": True,
    }



def test_status_api_translates_expected_workspace_error() -> None:
    app = create_app(workspace_dir=Path("/missing"))
    with patch(
        "lza_workbench.web.status.get_root_status_workflow",
        side_effect=LzaError("Workspace metadata is missing."),
    ):
        response = TestClient(app).get("/api/status")

    assert response.status_code == 422
    assert response.json() == {
        "error": {"code": "workspace_unavailable", "message": "Workspace metadata is missing."}
    }


def test_root_serves_static_overview() -> None:
    response = TestClient(create_app(workspace_dir=Path("/workspaces/acme"))).get("/")

    assert response.status_code == 200
    assert 'src="/js/app.js"' in response.text


def test_status_api_serializes_config_status() -> None:
    app = create_app(workspace_dir=Path("/workspaces/acme"))
    with patch(
        "lza_workbench.web.status.get_config_status_workflow",
        return_value=_config_status_result(),
    ):
        response = TestClient(app).get("/api/status/config")

    assert response.status_code == 200
    data = response.json()
    assert data["workspace"]["customerName"] == "Acme"
    assert data["workspace"]["yamlFilesCount"] == 2
    assert data["workspace"]["yamlFiles"] == ["accounts-config.yaml", "global-config.yaml"]
    assert data["localGit"]["isGit"] is True
    assert data["localGit"]["workingTree"]["branch"] == "main"
    assert data["repository"]["type"] == "s3"
    assert data["repository"]["bucket"] == "acme-config-bucket"
    assert data["repository"]["objectExists"] is True
    assert data["pipeline"]["name"] == "AWSAccelerator-Pipeline"
    assert data["pipeline"]["status"] == "Succeeded"
    assert data["remoteSync"]["status"] == "Synchronized"
    assert data["remoteSync"]["isSynced"] is True
    assert data["synchronization"]["hasState"] is True
    assert data["warnings"] == ["Test warning message"]


def test_config_status_api_translates_expected_workspace_error() -> None:
    app = create_app(workspace_dir=Path("/missing"))
    with patch(
        "lza_workbench.web.status.get_config_status_workflow",
        side_effect=LzaError("Configuration directory missing."),
    ):
        response = TestClient(app).get("/api/status/config")

    assert response.status_code == 422
    assert response.json() == {
        "error": {"code": "workspace_unavailable", "message": "Configuration directory missing."}
    }


def _workspace_config() -> WorkspaceConfig:
    return WorkspaceConfig.model_validate({
        "schema_version": 2,
        "customer": {"name": "Acme", "slug": "acme"},
        "lza": {"version": "1.11.0", "accelerator_prefix": "AWSAccelerator"},
        "aws": {"profile": "acme-admin", "region": "eu-west-1", "account_id": "123456789012"},
        "installer": {
            "stack_name": "AWSAccelerator-InstallerStack",
            "source_code": {
                "repository_type": "codecommit",
                "repository_name": "aws-accelerator-codecommit",
                "branch": "main",
            },
            "options": {
                "management_account_email": "mgmt@acme.com",
                "log_archive_account_email": "log@acme.com",
                "audit_account_email": "audit@acme.com",
                "control_tower_enabled": True,
                "enable_approval_stage": False,
            },
        },
    })


def _installer_status_result() -> InstallerStatusResult:
    cfg = _workspace_config()
    return InstallerStatusResult(
        workspace_dir=Path("/workspaces/acme"),
        config=cfg,
        state=None,
        profile="acme-admin",
        region="eu-west-1",
        aws_identity={"account": "123456789012", "arn": "arn:aws:iam::123456789012:user/admin"},
        aws_error=None,
        cfn_status=CfnStackStatusResult(
            stack_name="AWSAccelerator-InstallerStack",
            exists=True,
            stack_status="CREATE_COMPLETE",
            stack_id="arn:aws:cloudformation:eu-west-1:123456789012:stack/AWSAccelerator-InstallerStack/xyz",
            deployed_parameters={"AcceleratorPrefix": "AWSAccelerator"},
        ),
        deployed_version="1.11.0",
        configuration_drift={"AcceleratorPrefix": ("AWSAccelerator-Old", "AWSAccelerator")},
        state_alignment=StateAlignment(
            in_sync=True,
        ),
        installer_pipeline_name="AWSAccelerator-Installer",
        pipeline_state=PipelineStateResult(
            pipeline_name="AWSAccelerator-Installer",
            exists=True,
            status="Succeeded",
        ),
    )


def _installer_form() -> InstallerForm:
    return InstallerForm(
        workspace_dir=Path("/workspaces/acme"),
        template_path=Path("/workspaces/acme/.lza/template.yaml"),
        fields=(
            InstallerFormField(
                name="RepositorySource",
                label="Source location",
                default="codecommit",
                required=True,
                allowed_values=("codecommit", "s3", "github"),
                allowed_pattern=None,
                description="Repository source type",
            ),
            InstallerFormField(
                name="ManagementAccountEmail",
                label="Management account email",
                default="mgmt@acme.com",
                required=True,
                allowed_values=(),
                allowed_pattern="^.+@.+$",
                description="Management email",
            ),
        ),
        resolved_parameters={
            "RepositorySource": "codecommit",
            "ManagementAccountEmail": "mgmt@acme.com",
        },
    )


def _installer_plan_result() -> InstallerPlanResult:
    cfg = _workspace_config()
    return InstallerPlanResult(
        workspace_dir=Path("/workspaces/acme"),
        config=cfg,
        profile="acme-admin",
        region="eu-west-1",
        aws_identity={"account": "123456789012", "arn": "arn:aws:iam::123456789012:user/admin"},
        aws_error=None,
        codecommit_plan=CodeCommitPlanResult(
            repository_name="aws-accelerator-codecommit",
            branch_name="main",
            status="EXISTS",
            creation_required=False,
            sync_required=False,
            official_repo_url="https://github.com/awslabs/landing-zone-accelerator-on-aws",
            official_version_ref="v1.11.0",
            actions=[],
        ),
        cloudformation_plan=CfnDeploymentPlanResult(
            stack_name="AWSAccelerator-InstallerStack",
            operation="UPDATE",
            stack_status="CREATE_COMPLETE",
            resolved_parameters={"AcceleratorPrefix": "AWSAccelerator"},
            parameter_diffs={"AcceleratorPrefix": ("AWSAccelerator-Old", "AWSAccelerator")},
        ),
        dry_run=True,
        github_secret_warning=None,
    )


def test_installer_status_api_serializes_status_and_form() -> None:
    app = create_app(workspace_dir=Path("/workspaces/acme"))
    with (
        patch(
            "lza_workbench.web.status.get_installer_status_workflow",
            return_value=_installer_status_result(),
        ),
        patch(
            "lza_workbench.web.status.get_installer_parameters_schema",
            return_value=_installer_form(),
        ),
    ):
        response = TestClient(app).get("/api/status/installer")

    assert response.status_code == 200
    data = response.json()
    assert data["workspace"]["customerName"] == "Acme"
    assert data["canonicalSettings"]["acceleratorPrefix"] == "AWSAccelerator"
    assert data["canonicalSettings"]["managementAccountEmail"] == "mgmt@acme.com"
    assert data["canonicalSettings"]["controlTowerEnabled"] is True
    assert data["deployed"]["stackName"] == "AWSAccelerator-InstallerStack"
    assert data["deployed"]["stackStatus"] == "CREATE_COMPLETE"
    assert data["deployed"]["deployedVersion"] == "1.11.0"
    assert data["alignment"]["status"] == "In Sync"
    assert data["alignment"]["inSync"] is True
    assert "AcceleratorPrefix" in data["alignment"]["configurationDrift"]
    assert data["pipeline"]["name"] == "AWSAccelerator-Installer"
    assert data["pipeline"]["status"] == "Succeeded"
    assert len(data["form"]["fields"]) == 2
    assert data["form"]["fields"][0]["name"] == "RepositorySource"
    assert data["form"]["fields"][0]["allowedValues"] == ["codecommit", "s3", "github"]
    assert data["form"]["fields"][1]["allowedPattern"] == "^.+@.+$"
    assert data["form"]["resolvedParameters"]["ManagementAccountEmail"] == "mgmt@acme.com"


def test_save_installer_settings_api_success() -> None:
    app = create_app(workspace_dir=Path("/workspaces/acme"))
    cfg = _workspace_config()
    mock_res = InstallerSettingsResult(
        workspace_dir=Path("/workspaces/acme"),
        config=cfg,
        template_path=Path("/workspaces/acme/.lza/template.yaml"),
        resolved_parameters={"RepositorySource": "codecommit"},
        dry_run=False,
        no_save=False,
    )
    with patch(
        "lza_workbench.web.status.apply_installer_settings",
        return_value=mock_res,
    ):
        response = TestClient(app).post(
            "/api/installer/settings",
            json={"values": {"RepositorySource": "codecommit"}},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["message"] == "Installer settings saved successfully."
    assert data["resolvedParameters"] == {"RepositorySource": "codecommit"}


def test_save_installer_settings_api_validation_error() -> None:
    app = create_app(workspace_dir=Path("/workspaces/acme"))
    with patch(
        "lza_workbench.web.status.apply_installer_settings",
        side_effect=LzaError("Missing required parameter: ManagementAccountEmail"),
    ):
        response = TestClient(app).post(
            "/api/installer/settings",
            json={"values": {"RepositorySource": "codecommit"}},
        )

    assert response.status_code == 422
    assert (
        response.json()["error"]["message"]
        == "Missing required parameter: ManagementAccountEmail"
    )


def test_installer_plan_api_serializes_plan() -> None:
    app = create_app(workspace_dir=Path("/workspaces/acme"))
    with patch(
        "lza_workbench.web.status.plan_installer_workflow",
        return_value=_installer_plan_result(),
    ):
        response = TestClient(app).post("/api/installer/plan")

    assert response.status_code == 200
    data = response.json()
    assert data["cloudformation"]["stackName"] == "AWSAccelerator-InstallerStack"
    assert data["cloudformation"]["operation"] == "UPDATE"
    assert data["cloudformation"]["parameterDiffs"]["AcceleratorPrefix"] == {
        "deployed": "AWSAccelerator-Old",
        "target": "AWSAccelerator",
    }
    assert data["codecommit"]["repositoryName"] == "aws-accelerator-codecommit"
    assert data["codecommit"]["status"] == "EXISTS"


def test_config_pull_prepare_api_requires_confirmation() -> None:
    app = create_app(workspace_dir=Path("/workspaces/acme"))
    prep = ConfigPullPreparation(
        result=ConfigPullResult(
            workspace_dir=Path("/workspaces/acme"),
            config_dir=Path("/workspaces/acme/aws-accelerator-config"),
            repository_type="s3",
            dry_run=True,
            s3_bucket="acme-bucket",
            s3_key="archive.zip",
        ),
        confirmation_message=(
            "Local configuration has uncommitted changes that will be overwritten."
        ),
    )
    with patch(
        "lza_workbench.web.status.prepare_config_pull",
        return_value=prep,
    ):
        response = TestClient(app).post("/api/config/pull/prepare")

    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "pull"
    assert data["repositoryType"] == "s3"
    assert data["target"] == "s3://acme-bucket/archive.zip"
    assert data["requiresConfirmation"] is True
    assert "uncommitted changes" in data["confirmationReason"]


def test_config_pull_apply_api_success() -> None:
    app = create_app(workspace_dir=Path("/workspaces/acme"))
    pull_res = ConfigPullResult(
        workspace_dir=Path("/workspaces/acme"),
        config_dir=Path("/workspaces/acme/aws-accelerator-config"),
        repository_type="s3",
        dry_run=False,
        s3_bucket="acme-bucket",
        s3_key="archive.zip",
        extracted=True,
        diff_result=ConfigDiffResult(added=["new-file.yaml"], modified=[], removed=[]),
    )
    with patch(
        "lza_workbench.web.status.apply_config_pull",
        return_value=pull_res,
    ):
        response = TestClient(app).post(
            "/api/config/pull/apply",
            json={"overwrite_confirmed": True, "force": False},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["action"] == "pull"
    assert data["target"] == "s3://acme-bucket/archive.zip"
    assert data["diff"]["added"] == ["new-file.yaml"]
    assert data["diff"]["total"] == 1


def test_config_push_prepare_api() -> None:
    app = create_app(workspace_dir=Path("/workspaces/acme"))
    prep = ConfigPushPreparation(
        result=ConfigPushResult(
            workspace_dir=Path("/workspaces/acme"),
            config_dir=Path("/workspaces/acme/aws-accelerator-config"),
            repository_type="git",
            dry_run=True,
            git_remote="origin",
            git_remote_url="https://github.com/org/repo.git",
            git_branch="main",
            files_count=12,
        ),
        confirmation_message=None,
    )
    with patch(
        "lza_workbench.web.status.prepare_config_push",
        return_value=prep,
    ):
        response = TestClient(app).post("/api/config/push/prepare")

    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "push"
    assert data["repositoryType"] == "git"
    assert data["branch"] == "main"
    assert data["requiresConfirmation"] is False
    assert data["trackedFiles"] == 12


def test_config_push_apply_api_success() -> None:
    app = create_app(workspace_dir=Path("/workspaces/acme"))
    push_res = ConfigPushResult(
        workspace_dir=Path("/workspaces/acme"),
        config_dir=Path("/workspaces/acme/aws-accelerator-config"),
        repository_type="s3",
        dry_run=False,
        s3_bucket="acme-bucket",
        s3_key="archive.zip",
        etag="etag-456",
        version_id="ver-789",
    )
    with patch(
        "lza_workbench.web.status.apply_config_push",
        return_value=push_res,
    ):
        response = TestClient(app).post(
            "/api/config/push/apply",
            json={"overwrite_confirmed": True, "force": False},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["action"] == "push"
    assert data["etag"] == "etag-456"
    assert data["versionId"] == "ver-789"


def test_pipeline_snapshot_api_success() -> None:
    app = create_app(workspace_dir=Path("/workspaces/acme"))
    snapshot = PipelineSnapshotResult(
        workspace_dir=Path("/workspaces/acme"),
        customer_name="Acme",
        pipeline_name="AWSAccelerator-Pipeline",
        pipeline_type="configuration",
        pipeline_arn="arn:aws:codepipeline:eu-west-1:123456789012:AWSAccelerator-Pipeline",
        execution_id="exec-12345",
        status="InProgress",
        status_summary="Pipeline is actively executing",
        is_terminal=False,
        stages=[
            PipelineStageState(
                stage_name="Source",
                status="Succeeded",
                actions=[
                    PipelineActionState(action_name="Configuration", status="Succeeded"),
                ],
            ),
            PipelineStageState(
                stage_name="Build",
                status="InProgress",
                actions=[
                    PipelineActionState(action_name="Synthesize", status="InProgress"),
                ],
            ),
        ],
        start_time="2026-03-01T10:00:00Z",
        duration_seconds=125.0,
        current_stage="Build",
        current_action="Synthesize",
        is_live=True,
    )
    with patch(
        "lza_workbench.web.status.get_pipeline_snapshot_workflow",
        return_value=snapshot,
    ):
        response = TestClient(app).get("/api/pipeline/snapshot?type=configuration")

    assert response.status_code == 200
    data = response.json()
    assert data["pipelineName"] == "AWSAccelerator-Pipeline"
    assert data["executionId"] == "exec-12345"
    assert data["status"] == "InProgress"
    assert data["isTerminal"] is False
    assert data["currentStage"] == "Build"
    assert data["currentAction"] == "Synthesize"
    assert len(data["stages"]) == 2


def test_pipeline_diagnostics_api_success() -> None:
    app = create_app(workspace_dir=Path("/workspaces/acme"))
    failure = PipelineActionFailure(
        stage_name="Build",
        action_name="Synthesize",
        summary="Action execution failed",
        error_message="Build failed with error",
        external_execution_id="build-abc",
        external_execution_url="https://console.aws.amazon.com/codesuite/codebuild",
        diagnostic_details=["CloudFormation template validation error: Parameter missing"],
        raw_diagnostic_details=["raw error"],
        failed_resource="AWSAccelerator-SynthesizeStack",
        root_cause=FailureDiagnostic(
            message="CloudFormation template validation error: Parameter missing",
            category=FailureCategory.CLOUDFORMATION,
            raw_text="raw error",
            resource="AWSAccelerator-SynthesizeStack",
        ),
    )
    with patch(
        "lza_workbench.web.status.get_pipeline_diagnostics_workflow",
        return_value=[failure],
    ):
        response = TestClient(app).get("/api/pipeline/diagnostics?type=configuration")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["stageName"] == "Build"
    assert data[0]["actionName"] == "Synthesize"
    assert data[0]["failedResource"] == "AWSAccelerator-SynthesizeStack"
    assert data[0]["rootCause"]["category"] == "cloudformation"


def test_config_deploy_api_success() -> None:
    app = create_app(workspace_dir=Path("/workspaces/acme"))
    push_res = ConfigPushResult(
        workspace_dir=Path("/workspaces/acme"),
        config_dir=Path("/workspaces/acme/aws-accelerator-config"),
        repository_type="git",
        dry_run=False,
        git_branch="main",
        files_count=10,
    )
    start_res = PipelineStartResult(
        workspace_dir=Path("/workspaces/acme"),
        customer_name="Acme",
        pipeline_name="AWSAccelerator-Pipeline",
        pipeline_arn="arn:aws:codepipeline:eu-west-1:123456789012:AWSAccelerator-Pipeline",
        profile="acme-admin",
        region="eu-west-1",
        account_id="123456789012",
        dry_run=False,
        execution_id="exec-new-999",
    )
    deploy_res = ConfigDeployResult(
        push_result=push_res,
        start_result=start_res,
        dry_run=False,
    )
    with patch(
        "lza_workbench.web.status.deploy_configuration_workflow",
        return_value=deploy_res,
    ):
        response = TestClient(app).post(
            "/api/config/deploy",
            json={"overwrite_confirmed": True, "force": False},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["action"] == "deploy"
    assert data["pipelineStarted"] is True
    assert data["executionId"] == "exec-new-999"
    assert data["pushResult"]["filesCount"] == 10


def _sample_bootstrap_plan(
    *,
    imported: bool = False,
    cc_planned_op: str = "NO_CHANGE",
    is_live: bool = True,
    error: str | None = None,
) -> BootstrapPlanResult:
    return BootstrapPlanResult(
        workspace_dir=Path("/workspaces/acme"),
        config=WorkspaceConfig(
            customer=CustomerConfig(name="Acme", slug="acme"),
            aws=AwsConfig(profile="acme-admin", region="eu-west-1"),
        ),
        aws_profile="acme-admin",
        aws_region="eu-west-1",
        account_id="123456789012",
        bucket_name="lza-workbench-assets-123456789012-eu-west-1",
        bucket_exists=True,
        versioning_enabled=True,
        encryption_enabled=True,
        bucket_planned_operation="NO_CHANGE",
        codecommit_repo_name="aws-accelerator-config",
        codecommit_branch_name="main",
        codecommit_repo_exists=True if cc_planned_op != "MISSING" else False,
        codecommit_branch_exists=True if cc_planned_op != "MISSING" else False,
        codecommit_repo_planned_operation=cc_planned_op,
        github_secret_name=None,
        github_secret_exists=False,
        github_secret_accessible=False,
        github_repo_owner=None,
        github_repo_name=None,
        github_repo_branch=None,
        github_repo_accessible=False,
        github_planned_operation="NO_CHANGE",
        planned_operation=cc_planned_op if cc_planned_op != "NO_CHANGE" else "NO_CHANGE",
        actions=[
            BootstrapAction(
                subject="S3 Bucket",
                operation="NO_CHANGE",
                message="Bucket exists and is configured.",
            )
        ],
        warnings=[],
        dry_run=True,
        imported=imported,
        is_live=is_live,
        error=error,
    )


def test_bootstrap_plan_api_success() -> None:
    app = create_app(workspace_dir=Path("/workspaces/acme"))
    plan = _sample_bootstrap_plan()
    with patch("lza_workbench.web.status.plan_bootstrap_workflow", return_value=plan):
        response = TestClient(app).get("/api/bootstrap/plan")

    assert response.status_code == 200
    data = response.json()
    assert data["awsProfile"] == "acme-admin"
    assert data["accountId"] == "123456789012"
    assert data["plannedOperation"] == "NO_CHANGE"
    assert data["isMutationRequired"] is False
    assert data["imported"] is False
    assert data["isLive"] is True
    assert data["error"] is None
    assert data["resources"]["bucket"]["name"] == "lza-workbench-assets-123456789012-eu-west-1"
    assert len(data["actions"]) == 1
    assert data["actions"][0]["operation"] == "NO_CHANGE"


def test_bootstrap_plan_api_imported_missing() -> None:
    app = create_app(workspace_dir=Path("/workspaces/acme"))
    plan = _sample_bootstrap_plan(imported=True, cc_planned_op="MISSING")
    with patch("lza_workbench.web.status.plan_bootstrap_workflow", return_value=plan):
        response = TestClient(app).get("/api/bootstrap/plan")

    assert response.status_code == 200
    data = response.json()
    assert data["imported"] is True
    assert data["isBlocked"] is True
    assert data["resources"]["codecommit"]["plannedOperation"] == "MISSING"


def test_bootstrap_plan_api_offline() -> None:
    app = create_app(workspace_dir=Path("/workspaces/acme"))
    plan = _sample_bootstrap_plan(
        is_live=False,
        error="SSO session expired",
    )
    with patch("lza_workbench.web.status.plan_bootstrap_workflow", return_value=plan):
        response = TestClient(app).get("/api/bootstrap/plan")

    assert response.status_code == 200
    data = response.json()
    assert data["isLive"] is False
    assert data["error"] == "SSO session expired"
    assert data["isMutationRequired"] is False


def test_bootstrap_apply_api_success() -> None:
    app = create_app(workspace_dir=Path("/workspaces/acme"))
    result = WorkspaceBootstrapResult(
        workspace_dir=Path("/workspaces/acme"),
        config=WorkspaceConfig(
            customer=CustomerConfig(name="Acme", slug="acme"),
            aws=AwsConfig(profile="acme-admin", region="eu-west-1"),
        ),
        aws_profile="acme-admin",
        aws_region="eu-west-1",
        account_id="123456789012",
        bucket_name="lza-workbench-assets-123456789012-eu-west-1",
        codecommit_repo_name="aws-accelerator-config",
        codecommit_branch_name="main",
        codecommit_repo_planned_operation="NO_CHANGE",
        github_secret_name=None,
        github_secret_created=False,
        github_repo_owner=None,
        github_repo_name=None,
        github_repo_branch=None,
        github_repo_accessible=False,
        github_planned_operation="NO_CHANGE",
        planned_operation="NO_CHANGE",
        dry_run=False,
        skipped=False,
        actions_taken=["Verified S3 bucket"],
        warnings=[],
    )
    with patch("lza_workbench.web.status.bootstrap_workspace_workflow", return_value=result):
        response = TestClient(app).post(
            "/api/bootstrap/apply",
            json={"allow_missing_github_secret": False},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["actionsTaken"] == ["Verified S3 bucket"]


def test_bootstrap_apply_api_error() -> None:
    app = create_app(workspace_dir=Path("/workspaces/acme"))
    with patch(
        "lza_workbench.web.status.bootstrap_workspace_workflow",
        side_effect=LzaError("Missing imported CodeCommit repository cannot be recreated."),
    ):
        response = TestClient(app).post("/api/bootstrap/apply", json={})

    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "workspace_unavailable"
    assert "Missing imported CodeCommit repository" in data["error"]["message"]


def test_workspace_active_api() -> None:
    from lza_workbench.web.status import ActiveWorkspaceContext
    from lza_workbench.workspace.context import WorkspaceAssessment

    context = ActiveWorkspaceContext(Path("/workspaces/acme"))
    app = create_app(workspace_dir=context)

    dummy_root = RootStatusResult(
        workspace_dir=Path("/workspaces/acme"),
        customer_name="Acme",
        lza_version="v1.15.5",
        profile="acme-root",
        region="us-east-1",
        aws_identity=None,
        aws_error=None,
        installer=InstallerStackSummary(name="AWSAccelerator-InstallerStack", exists=False),
        installer_pipeline=PipelineSummary(name="AWSAccelerator-Pipeline", exists=False),
        configuration_repo=ConfigurationRepoSummary(repository_type="S3"),
        configuration_pipeline=PipelineSummary(name="AWSAccelerator-ConfigPipeline", exists=False),
        health=OverallHealthSummary(
            installer="Not Deployed", configuration="Clean", workspace="Clean"
        ),
        assessment=WorkspaceAssessment(
            metadata_valid=True,
            configuration_present=True,
            installer_configured=False,
            installer_recorded_deployed=False,
            imported=False,
        ),
    )

    with patch("lza_workbench.web.status.get_root_status_workflow", return_value=dummy_root):
        response = TestClient(app).get("/api/workspace/active")

    assert response.status_code == 200
    data = response.json()
    assert data["hasWorkspace"] is True
    assert data["workspaceDir"] == "/workspaces/acme"
    assert data["customerName"] == "Acme"
    assert data["assessment"]["installerConfigured"] is False
    assert data["assessment"]["configurationPresent"] is True


def test_workspace_open_api(tmp_path: Path) -> None:
    from lza_workbench.web.status import ActiveWorkspaceContext

    context = ActiveWorkspaceContext(None)
    app = create_app(workspace_dir=context)

    target_ws = tmp_path / "customer-a"
    target_ws.mkdir()

    dummy_root = RootStatusResult(
        workspace_dir=target_ws,
        customer_name="Customer A",
        lza_version="v1.15.5",
        profile="cust-a-root",
        region="us-east-1",
        aws_identity=None,
        aws_error=None,
        installer=InstallerStackSummary(name="AWSAccelerator-InstallerStack", exists=False),
        installer_pipeline=PipelineSummary(name="AWSAccelerator-Pipeline", exists=False),
        configuration_repo=ConfigurationRepoSummary(repository_type="S3"),
        configuration_pipeline=PipelineSummary(name="AWSAccelerator-ConfigPipeline", exists=False),
        health=OverallHealthSummary(
            installer="Not Deployed", configuration="Clean", workspace="Clean"
        ),
    )

    with patch("lza_workbench.web.status.get_root_status_workflow", return_value=dummy_root):
        response = TestClient(app).post("/api/workspace/open", json={"directory": str(target_ws)})

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["workspaceDir"] == str(target_ws.resolve())
    assert context.workspace_dir == target_ws.resolve()


def test_workspace_init_preview_and_apply(tmp_path: Path) -> None:
    from lza_workbench.web.status import ActiveWorkspaceContext
    from lza_workbench.workflows.workspace_init import WorkspaceInitResult
    from lza_workbench.workspace.schema import (
        AwsConfig,
        CustomerConfig,
        LzaConfig,
        WorkspaceConfig,
        WorkspaceState,
    )

    context = ActiveWorkspaceContext(None)
    app = create_app(workspace_dir=context)

    ws_dir = tmp_path / "new-customer"
    cfg = WorkspaceConfig(
        customer=CustomerConfig(name="New Customer", slug="new-customer"),
        aws=AwsConfig(profile="new-customer-root", region="us-east-1"),
        lza=LzaConfig(version="v1.15.5"),
    )
    state = WorkspaceState.from_config(cfg)

    preview_res = WorkspaceInitResult(
        workspace_dir=ws_dir,
        config=cfg,
        state=state,
        planned_paths=[ws_dir / "lza-workspace.yaml", ws_dir / ".lza" / "state.json"],
        existing_directory=False,
        identity=None,
        dry_run=True,
    )
    apply_res = WorkspaceInitResult(
        workspace_dir=ws_dir,
        config=cfg,
        state=state,
        planned_paths=[ws_dir / "lza-workspace.yaml", ws_dir / ".lza" / "state.json"],
        existing_directory=False,
        identity=None,
        dry_run=False,
    )

    with patch("lza_workbench.web.status.init_workspace_workflow", return_value=preview_res):
        resp_preview = TestClient(app).post(
            "/api/workspace/init/preview",
            json={"customer_name": "New Customer"},
        )
    assert resp_preview.status_code == 200
    preview_data = resp_preview.json()
    assert preview_data["customerSlug"] == "new-customer"
    assert preview_data["dryRun"] is True

    with patch("lza_workbench.web.status.init_workspace_workflow", return_value=apply_res):
        resp_apply = TestClient(app).post(
            "/api/workspace/init/apply",
            json={"customer_name": "New Customer"},
        )
    assert resp_apply.status_code == 200
    apply_data = resp_apply.json()
    assert apply_data["customerSlug"] == "new-customer"
    assert apply_data["dryRun"] is False
    assert context.workspace_dir == ws_dir.resolve()


def test_workspace_import_discover_prepare_apply(tmp_path: Path) -> None:
    from lza_workbench.web.status import ActiveWorkspaceContext
    from lza_workbench.workflows.workspace_import import (
        ImportWorkspaceDiscovery,
        ImportWorkspacePreparation,
        WorkspaceImportResult,
    )
    from lza_workbench.workspace.schema import (
        AwsConfig,
        CustomerConfig,
        LzaConfig,
        WorkspaceConfig,
        WorkspaceState,
    )

    context = ActiveWorkspaceContext(None)
    app = create_app(workspace_dir=context)

    ws_dir = tmp_path / "imported-ws"
    cfg_dir = ws_dir / "config"
    cfg = WorkspaceConfig(
        customer=CustomerConfig(name="Imported Customer", slug="imported-customer"),
        aws=AwsConfig(profile="imported-root", region="us-east-1"),
        lza=LzaConfig(version="v1.15.5"),
    )
    state = WorkspaceState.from_config(cfg)
    state.imported = True

    discovery = ImportWorkspaceDiscovery(
        workspace_dir=ws_dir,
        config_dir=cfg_dir,
        existing=None,
    )

    from lza_workbench.configuration.git import GitProvenance

    prov = GitProvenance(
        remote_url="https://github.com/acme/lza-config.git",
        branch="main",
        commit="1234567890abcdef",
        files_count=12,
        repo_type="github",
        repo_name="acme/lza-config",
    )

    import_res = WorkspaceImportResult(
        workspace_dir=ws_dir,
        config_dir=cfg_dir,
        config=cfg,
        state=state,
        affected_paths=[ws_dir / "lza-workspace.yaml", ws_dir / ".lza" / "state.json"],
        identity=None,
        already_imported=False,
        dry_run=False,
        provenance=prov,
        recommendations=["Run bootstrap next"],
    )
    prep = ImportWorkspacePreparation(result=import_res)

    with patch("lza_workbench.web.status.discover_import_workspace", return_value=discovery):
        resp_disc = TestClient(app).post(
            "/api/workspace/import/discover",
            json={"workspace_dir": str(ws_dir)},
        )
    assert resp_disc.status_code == 200
    assert resp_disc.json()["hasExistingMetadata"] is False

    with patch("lza_workbench.web.status.prepare_workspace_import", return_value=prep):
        resp_prep = TestClient(app).post(
            "/api/workspace/import/prepare",
            json={"workspace_dir": str(ws_dir)},
        )
    assert resp_prep.status_code == 200
    prep_data = resp_prep.json()
    assert prep_data["customerSlug"] == "imported-customer"
    assert prep_data["provenance"]["repoName"] == "acme/lza-config"
    assert prep_data["provenance"]["filesCount"] == 12
    assert prep_data["recommendations"] == ["Run bootstrap next"]
    assert context.prepared_import is not None

    with patch("lza_workbench.web.status.apply_workspace_import", return_value=import_res):
        resp_apply = TestClient(app).post("/api/workspace/import/apply")
    assert resp_apply.status_code == 200
    assert resp_apply.json()["customerSlug"] == "imported-customer"
    assert context.workspace_dir == ws_dir.resolve()





