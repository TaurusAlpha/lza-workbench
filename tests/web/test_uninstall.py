"""Focused Web uninstallation API tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import lza_workbench.interfaces.web.uninstall as web_uninstall
from lza_workbench.interfaces.web.app import create_app
from lza_workbench.workspace.schema import AwsConfig, CustomerConfig, WorkspaceConfig
from lza_workbench.workspace.uninstall.models import (
    UninstallAccountTarget,
    UninstallPlan,
    UninstallProgress,
    UninstallRetainedResource,
    UninstallS3Bucket,
    UninstallStack,
)
from lza_workbench.workspace.uninstall.state import RetainedResourceRecord


def _mock_workspace_context(slug: str = "acme"):
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Acme Corp", slug=slug),
        aws=AwsConfig(region="eu-west-1", profile="acme-mgmt", account_id="111111111111"),
    )
    context = MagicMock()
    context.config = config
    context.workspace_dir = Path("/workspaces/acme")
    return context


def _sample_uninstall_plan() -> UninstallPlan:
    now = datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC)
    return UninstallPlan(
        customer_name="Acme Corp",
        customer_slug="acme",
        accelerator_prefix="AWSAccelerator",
        accounts=[
            UninstallAccountTarget(
                account_id="111111111111",
                name="Management",
                is_management=True,
                role_name="AWSAccelerator-PipelineRole",
            )
        ],
        regions=["eu-west-1"],
        stacks=[
            UninstallStack(
                stack_name="AWSAccelerator-PipelineStack",
                account_id="111111111111",
                account_name="Management",
                region="eu-west-1",
                creation_time=now,
                termination_protection=False,
                is_pipeline_or_installer=True,
            )
        ],
        s3_buckets=[
            UninstallS3Bucket(
                bucket_name="aws-accelerator-config-111111111111-eu-west-1",
                account_id="111111111111",
                region="eu-west-1",
            )
        ],
        retained_resources=[
            UninstallRetainedResource(
                account_id="111111111111",
                region="eu-west-1",
                stack_name="AWSAccelerator-Logging",
                logical_id="LogGroup",
                physical_id="/aws/accelerator/log",
                resource_type="AWS::Logs::LogGroup",
            )
        ],
    )


def test_uninstall_plan_endpoint_success() -> None:
    app = create_app(workspace_dir=Path("/workspaces/acme"))
    mock_ctx = _mock_workspace_context()
    sample_plan = _sample_uninstall_plan()

    with (
        patch(
            "lza_workbench.interfaces.web.uninstall.load_workspace_context", return_value=mock_ctx
        ),
        patch(
            "lza_workbench.interfaces.web.uninstall.resolve_aws_execution_context"
        ) as mock_resolve,
        patch(
            "lza_workbench.interfaces.web.uninstall.build_uninstall_plan", return_value=sample_plan
        ) as mock_build,
    ):
        mock_resolve.return_value = MagicMock()
        response = TestClient(app).post(
            "/api/uninstall/plan",
            json={
                "regions": ["eu-west-1"],
                "all_regions": False,
                "accounts": ["111111111111"],
                "assume_role_name": "AWSAccelerator-PipelineRole",
                "skip_installer": True,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    plan = data["plan"]
    assert plan["customerSlug"] == "acme"
    assert plan["customerName"] == "Acme Corp"
    assert len(plan["accounts"]) == 1
    assert plan["accounts"][0]["accountId"] == "111111111111"
    assert len(plan["stacks"]) == 1
    assert plan["stacks"][0]["stackName"] == "AWSAccelerator-PipelineStack"
    assert len(plan["s3Buckets"]) == 1
    assert plan["s3Buckets"][0]["bucketName"] == "aws-accelerator-config-111111111111-eu-west-1"
    assert len(plan["retainedResources"]) == 1
    assert plan["totalStacks"] == 1
    assert plan["totalS3Buckets"] == 1
    assert plan["totalRetainedResources"] == 1

    mock_build.assert_called_once()
    options_arg = mock_build.call_args[1]["options"]
    assert options_arg.dry_run is True
    assert options_arg.skip_installer is True


def test_uninstall_apply_endpoint_slug_mismatch() -> None:
    app = create_app(workspace_dir=Path("/workspaces/acme"))
    mock_ctx = _mock_workspace_context(slug="acme")

    with patch(
        "lza_workbench.interfaces.web.uninstall.load_workspace_context", return_value=mock_ctx
    ):
        response = TestClient(app).post(
            "/api/uninstall/apply",
            json={"customer_slug_confirmation": "wrong-slug"},
        )

    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert "Confirmation slug mismatch" in data["error"]["message"]


def test_uninstall_apply_endpoint_already_running() -> None:
    app = create_app(workspace_dir=Path("/workspaces/acme"))
    mock_ctx = _mock_workspace_context(slug="acme")

    web_uninstall._is_uninstall_running = True
    try:
        with patch(
            "lza_workbench.interfaces.web.uninstall.load_workspace_context", return_value=mock_ctx
        ):
            response = TestClient(app).post(
                "/api/uninstall/apply",
                json={"customer_slug_confirmation": "acme"},
            )

        assert response.status_code == 422
        assert "already currently running" in response.json()["error"]["message"]
    finally:
        web_uninstall._is_uninstall_running = False


def test_uninstall_apply_endpoint_success() -> None:
    app = create_app(workspace_dir=Path("/workspaces/acme"))
    mock_ctx = _mock_workspace_context(slug="acme")
    sample_plan = _sample_uninstall_plan()

    with (
        patch(
            "lza_workbench.interfaces.web.uninstall.load_workspace_context", return_value=mock_ctx
        ),
        patch(
            "lza_workbench.interfaces.web.uninstall.resolve_aws_execution_context"
        ) as mock_resolve,
        patch(
            "lza_workbench.interfaces.web.uninstall.build_uninstall_plan", return_value=sample_plan
        ),
        patch("lza_workbench.interfaces.web.uninstall.execute_uninstall"),
        patch("threading.Thread") as mock_thread_cls,
    ):
        mock_resolve.return_value = MagicMock()
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        response = TestClient(app).post(
            "/api/uninstall/apply",
            json={
                "customer_slug_confirmation": "acme",
                "delete_s3_buckets": True,
                "selected_bucket_names": ["aws-accelerator-config-111111111111-eu-west-1"],
                "delete_retained_resources": True,
                "selected_retained_ids": ["/aws/accelerator/log"],
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "IN_PROGRESS"
    mock_thread.start.assert_called_once()


def test_uninstall_progress_endpoint() -> None:
    app = create_app(workspace_dir=Path("/workspaces/acme"))
    mock_ctx = _mock_workspace_context(slug="acme")
    progress = UninstallProgress(
        status="IN_PROGRESS",
        customer_slug="acme",
        started_at="2026-03-01T10:00:00Z",
        deleted_stacks=["stack-1", "stack-2", "stack-3"],
        failed_stacks=[],
        deleted_buckets=["bucket-1"],
        deleted_retained=[{"id": "res-1"}, {"id": "res-2"}],
        retained_resources_remaining=[{"id": "res-3"}, {"id": "res-4"}],
    )
    retained_records = [
        RetainedResourceRecord(
            account_id="111111111111",
            region="eu-west-1",
            stack_name="AWSAccelerator-Logging",
            logical_id="LogGroup",
            physical_id="/aws/accelerator/log",
            resource_type="AWS::Logs::LogGroup",
            status="deleted",
        )
    ]

    with (
        patch(
            "lza_workbench.interfaces.web.uninstall.load_workspace_context", return_value=mock_ctx
        ),
        patch(
            "lza_workbench.interfaces.web.uninstall.load_or_init_progress", return_value=progress
        ),
        patch(
            "lza_workbench.interfaces.web.uninstall.read_retained_resources_from_state",
            return_value=retained_records,
        ),
    ):
        response = TestClient(app).get("/api/uninstall/progress")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "IN_PROGRESS"
    assert data["customerSlug"] == "acme"
    assert len(data["deletedStacks"]) == 3
    assert len(data["deletedBuckets"]) == 1
    assert len(data["deletedRetained"]) == 2
    assert len(data["retainedInState"]) == 1
    assert data["retainedInState"][0]["physicalId"] == "/aws/accelerator/log"
    assert data["retainedInState"][0]["status"] == "deleted"
