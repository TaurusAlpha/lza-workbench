"""Focused Web status API tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from lza_workbench.errors import LzaError
from lza_workbench.web.app import create_app
from lza_workbench.workflows.status_root import (
    ConfigurationRepoSummary,
    InstallerStackSummary,
    OverallHealthSummary,
    PipelineSummary,
    RootStatusResult,
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
        configuration_repo=ConfigurationRepoSummary(repository_type="s3", target="acme-config"),
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
