"""Focused Web status API tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

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
from lza_workbench.web.app import create_app
from lza_workbench.workflows.status_root import (
    ConfigurationRepoSummary,
    InstallerStackSummary,
    OverallHealthSummary,
    PipelineSummary,
    RootStatusResult,
)


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
