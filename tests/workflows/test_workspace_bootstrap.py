"""Tests for workspace bootstrap workflows."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from lza_workbench.workflows.workspace_bootstrap import (
    bootstrap_workspace_workflow,
    ensure_s3_workbench_assets_bucket,
    get_workbench_assets_bucket_name,
    plan_bootstrap_workflow,
)
from lza_workbench.workspace.config import load_workspace_config
from lza_workbench.workspace.state import load_workspace_state


def test_get_workbench_assets_bucket_name() -> None:
    bucket_name = get_workbench_assets_bucket_name("123456789012", "us-east-1")
    assert bucket_name == "s3-lza-workbench-assets-123456789012-us-east-1"

    bucket_name_eu = get_workbench_assets_bucket_name("987654321098", "eu-central-1")
    assert bucket_name_eu == "s3-lza-workbench-assets-987654321098-eu-central-1"


def test_ensure_s3_workbench_assets_bucket_new_bucket() -> None:
    mock_s3 = MagicMock()
    mock_s3.head_bucket.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}},
        "HeadBucket",
    )
    actions = ensure_s3_workbench_assets_bucket(
        client=mock_s3,
        bucket_name="s3-lza-workbench-assets-123456789012-us-east-1",
        region="us-east-1",
    )
    mock_s3.create_bucket.assert_called_once_with(
        Bucket="s3-lza-workbench-assets-123456789012-us-east-1"
    )
    mock_s3.put_bucket_versioning.assert_called_once()
    mock_s3.put_bucket_encryption.assert_called_once()
    assert len(actions) == 3


def test_plan_bootstrap_workflow_create(initialized_workspace: Path) -> None:
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
    ):
        mock_val.return_value = {"account": "111222333444", "arn": "arn:aws:iam::111222333444:root"}
        mock_s3 = MagicMock()
        mock_s3.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}},
            "HeadBucket",
        )
        mock_client.return_value = mock_s3

        plan = plan_bootstrap_workflow(target_dir=initialized_workspace, dry_run=True)
        assert plan.planned_operation == "CREATE"
        assert plan.account_id == "111222333444"
        assert plan.bucket_name == "s3-lza-workbench-assets-111222333444-eu-west-1"
        assert plan.bucket_exists is False
        assert len(plan.actions) == 4


def test_plan_bootstrap_workflow_no_change(initialized_workspace: Path) -> None:
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
    ):
        mock_val.return_value = {"account": "111222333444", "arn": "arn:aws:iam::111222333444:root"}
        mock_s3 = MagicMock()
        mock_s3.head_bucket.return_value = {}
        mock_s3.get_bucket_versioning.return_value = {"Status": "Enabled"}
        mock_s3.get_bucket_encryption.return_value = {
            "ServerSideEncryptionConfiguration": {
                "Rules": [
                    {
                        "ApplyServerSideEncryptionByDefault": {
                            "SSEAlgorithm": "aws:kms",
                        }
                    }
                ]
            }
        }
        mock_client.return_value = mock_s3

        plan = plan_bootstrap_workflow(target_dir=initialized_workspace, dry_run=True)
        assert plan.planned_operation == "NO_CHANGE"
        assert plan.bucket_exists is True
        assert plan.versioning_enabled is True
        assert plan.encryption_enabled is True


def test_bootstrap_workspace_workflow_executes_and_saves_state(
    initialized_workspace: Path,
) -> None:
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
    ):
        mock_val.return_value = {"account": "111222333444", "arn": "arn:aws:iam::111222333444:root"}
        mock_s3 = MagicMock()
        mock_s3.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}},
            "HeadBucket",
        )
        mock_client.return_value = mock_s3

        result = bootstrap_workspace_workflow(
            target_dir=initialized_workspace,
            dry_run=False,
        )

        assert result.dry_run is False
        assert result.bucket_name == "s3-lza-workbench-assets-111222333444-eu-west-1"
        assert len(result.actions_taken) == 4

        # Verify config saved
        cfg = load_workspace_config(initialized_workspace)
        assert cfg.assets_bucket == "s3-lza-workbench-assets-111222333444-eu-west-1"

        # Verify state saved
        st = load_workspace_state(initialized_workspace)
        assert st.bootstrapped_at is not None
        assert st.management_account_id == "111222333444"


def test_plan_bootstrap_workflow_with_codecommit_create(initialized_workspace: Path) -> None:
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
    ):
        mock_val.return_value = {"account": "111222333444", "arn": "arn:aws:iam::111222333444:root"}
        mock_s3 = MagicMock()
        mock_s3.head_bucket.return_value = {}
        mock_s3.get_bucket_versioning.return_value = {"Status": "Enabled"}
        mock_s3.get_bucket_encryption.return_value = {
            "ServerSideEncryptionConfiguration": {
                "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "aws:kms"}}]
            }
        }
        mock_cc = MagicMock()
        mock_cc.get_repository.side_effect = ClientError(
            {"Error": {"Code": "RepositoryDoesNotExistException"}}, "GetRepository"
        )

        def client_factory(service: str):
            return mock_s3 if service == "s3" else mock_cc

        mock_client.side_effect = client_factory

        plan = plan_bootstrap_workflow(target_dir=initialized_workspace, dry_run=True)
        assert plan.bucket_planned_operation == "NO_CHANGE"
        assert plan.codecommit_repo_name == "lza-config-source"
        assert plan.codecommit_repo_planned_operation == "CREATE"
        assert plan.planned_operation == "CREATE"
        assert any("Create CodeCommit repository 'lza-config-source'" in a for a in plan.actions)


def test_plan_bootstrap_workflow_with_codecommit_imported_missing(
    imported_workspace: Path,
) -> None:
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
    ):
        mock_val.return_value = {"account": "111222333444", "arn": "arn:aws:iam::111222333444:root"}
        mock_s3 = MagicMock()
        mock_s3.head_bucket.return_value = {}
        mock_s3.get_bucket_versioning.return_value = {"Status": "Enabled"}
        mock_s3.get_bucket_encryption.return_value = {
            "ServerSideEncryptionConfiguration": {
                "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "aws:kms"}}]
            }
        }
        mock_cc = MagicMock()
        mock_cc.get_repository.side_effect = ClientError(
            {"Error": {"Code": "RepositoryDoesNotExistException"}}, "GetRepository"
        )

        def client_factory(service: str):
            return mock_s3 if service == "s3" else mock_cc

        mock_client.side_effect = client_factory

        plan = plan_bootstrap_workflow(target_dir=imported_workspace, dry_run=True)
        assert plan.codecommit_repo_planned_operation == "MISSING"
        assert plan.planned_operation == "MISSING"
        assert any("MISSING" in a for a in plan.actions)


def test_bootstrap_workspace_workflow_with_codecommit_create(initialized_workspace: Path) -> None:
    with (
        patch("lza_workbench.aws.client_factory.AwsClientFactory.validate_identity") as mock_val,
        patch("lza_workbench.aws.client_factory.AwsClientFactory.get_client") as mock_client,
    ):
        mock_val.return_value = {"account": "111222333444", "arn": "arn:aws:iam::111222333444:root"}
        mock_s3 = MagicMock()
        mock_s3.head_bucket.return_value = {}
        mock_s3.get_bucket_versioning.return_value = {"Status": "Enabled"}
        mock_s3.get_bucket_encryption.return_value = {
            "ServerSideEncryptionConfiguration": {
                "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "aws:kms"}}]
            }
        }
        mock_cc = MagicMock()
        mock_cc.get_repository.side_effect = ClientError(
            {"Error": {"Code": "RepositoryDoesNotExistException"}}, "GetRepository"
        )

        def client_factory(service: str):
            return mock_s3 if service == "s3" else mock_cc

        mock_client.side_effect = client_factory

        result = bootstrap_workspace_workflow(
            target_dir=initialized_workspace,
            dry_run=False,
        )

        assert result.dry_run is False
        assert result.codecommit_repo_name == "lza-config-source"
        assert any(
            "Created CodeCommit repository 'lza-config-source'" in a for a in result.actions_taken
        )
        mock_cc.create_repository.assert_called_once()
