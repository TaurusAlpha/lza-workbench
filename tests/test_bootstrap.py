"""Tests for LZA Workbench bootstrap command and workflows."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from typer.testing import CliRunner

from lza_workbench.aws.s3 import (
    create_s3_bucket,
    ensure_s3_workbench_assets_bucket,
    get_workbench_assets_bucket_name,
    inspect_s3_bucket,
    put_s3_bucket_encryption,
    put_s3_bucket_versioning,
)
from lza_workbench.cli.main import app
from lza_workbench.errors import LzaError
from lza_workbench.workflows.workspace_bootstrap import (
    bootstrap_workspace_workflow,
    plan_bootstrap_workflow,
)
from lza_workbench.workflows.workspace_init import init_workspace_workflow
from lza_workbench.workspace.config import load_workspace_config
from lza_workbench.workspace.state import load_workspace_state

runner = CliRunner()


@pytest.fixture
def test_workspace(tmp_path: Path) -> Path:
    ws_dir = tmp_path / "bootstrap-test"
    init_workspace_workflow(
        customer_name="Acme Corp",
        workspace_dir=ws_dir,
        aws_profile="acme-root",
        aws_region="eu-west-1",
        skip_aws_check=True,
    )
    return ws_dir


def test_get_workbench_assets_bucket_name() -> None:
    bucket_name = get_workbench_assets_bucket_name("123456789012", "us-east-1")
    assert bucket_name == "s3-lza-workbench-assets-123456789012-us-east-1"

    bucket_name_eu = get_workbench_assets_bucket_name("987654321098", "eu-central-1")
    assert bucket_name_eu == "s3-lza-workbench-assets-987654321098-eu-central-1"


def test_inspect_s3_bucket_not_found() -> None:
    mock_s3 = MagicMock()
    mock_s3.head_bucket.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}},
        "HeadBucket",
    )
    result = inspect_s3_bucket(client=mock_s3, bucket_name="test-bucket")
    assert result["exists"] is False
    assert result["accessible"] is False
    assert result["versioning_enabled"] is False
    assert result["kms_encrypted"] is False


def test_inspect_s3_bucket_exists_configured() -> None:
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
    result = inspect_s3_bucket(client=mock_s3, bucket_name="test-bucket")
    assert result["exists"] is True
    assert result["accessible"] is True
    assert result["versioning_enabled"] is True
    assert result["encryption_enabled"] is True
    assert result["kms_encrypted"] is True


def test_inspect_s3_bucket_access_denied() -> None:
    mock_s3 = MagicMock()
    mock_s3.head_bucket.side_effect = ClientError(
        {"Error": {"Code": "403", "Message": "Forbidden"}},
        "HeadBucket",
    )
    with pytest.raises(LzaError, match="Access denied to S3 bucket"):
        inspect_s3_bucket(client=mock_s3, bucket_name="test-bucket")


def test_create_s3_bucket_us_east_1() -> None:
    mock_s3 = MagicMock()
    create_s3_bucket(client=mock_s3, bucket_name="test-bucket", region="us-east-1")
    mock_s3.create_bucket.assert_called_once_with(Bucket="test-bucket")


def test_create_s3_bucket_other_region() -> None:
    mock_s3 = MagicMock()
    create_s3_bucket(client=mock_s3, bucket_name="test-bucket", region="eu-west-1")
    mock_s3.create_bucket.assert_called_once_with(
        Bucket="test-bucket",
        CreateBucketConfiguration={"LocationConstraint": "eu-west-1"},
    )


def test_create_s3_bucket_already_owned() -> None:
    mock_s3 = MagicMock()
    mock_s3.create_bucket.side_effect = ClientError(
        {"Error": {"Code": "BucketAlreadyOwnedByYou", "Message": "Owned"}},
        "CreateBucket",
    )
    # Should not raise
    create_s3_bucket(client=mock_s3, bucket_name="test-bucket", region="us-east-1")


def test_put_s3_bucket_versioning() -> None:
    mock_s3 = MagicMock()
    put_s3_bucket_versioning(client=mock_s3, bucket_name="test-bucket", enabled=True)
    mock_s3.put_bucket_versioning.assert_called_once_with(
        Bucket="test-bucket",
        VersioningConfiguration={"Status": "Enabled"},
    )


def test_put_s3_bucket_encryption() -> None:
    mock_s3 = MagicMock()
    put_s3_bucket_encryption(client=mock_s3, bucket_name="test-bucket")
    mock_s3.put_bucket_encryption.assert_called_once_with(
        Bucket="test-bucket",
        ServerSideEncryptionConfiguration={
            "Rules": [
                {
                    "ApplyServerSideEncryptionByDefault": {
                        "SSEAlgorithm": "aws:kms",
                    },
                    "BucketKeyEnabled": True,
                }
            ]
        },
    )


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


def test_plan_bootstrap_workflow_create(test_workspace: Path) -> None:
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

        plan = plan_bootstrap_workflow(target_dir=test_workspace, dry_run=True)
        assert plan.planned_operation == "CREATE"
        assert plan.account_id == "111222333444"
        assert plan.bucket_name == "s3-lza-workbench-assets-111222333444-eu-west-1"
        assert plan.bucket_exists is False
        assert len(plan.actions) == 3


def test_plan_bootstrap_workflow_no_change(test_workspace: Path) -> None:
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

        plan = plan_bootstrap_workflow(target_dir=test_workspace, dry_run=True)
        assert plan.planned_operation == "NO_CHANGE"
        assert plan.bucket_exists is True
        assert plan.versioning_enabled is True
        assert plan.encryption_enabled is True


def test_bootstrap_workspace_workflow_executes_and_saves_state(test_workspace: Path) -> None:
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
            target_dir=test_workspace,
            dry_run=False,
        )

        assert result.dry_run is False
        assert result.bucket_name == "s3-lza-workbench-assets-111222333444-eu-west-1"
        assert len(result.actions_taken) == 3

        # Verify config saved
        cfg = load_workspace_config(test_workspace)
        assert cfg.assets_bucket == "s3-lza-workbench-assets-111222333444-eu-west-1"

        # Verify state saved
        st = load_workspace_state(test_workspace)
        assert st.assets_bucket_name == "s3-lza-workbench-assets-111222333444-eu-west-1"
        assert st.bootstrapped_at is not None
        assert st.management_account_id == "111222333444"


def test_cli_bootstrap_dry_run(test_workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(test_workspace)
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

        res = runner.invoke(app, ["bootstrap", "--dry-run"])
        assert res.exit_code == 0
        assert "Dry run" in res.output
        assert "s3-lza-workbench-assets-111222333444-eu-west-1" in res.output


def test_cli_bootstrap_force(test_workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(test_workspace)
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

        res = runner.invoke(app, ["bootstrap", "--force"])
        assert res.exit_code == 0
        assert "ready" in res.output
        assert "s3-lza-workbench-assets-111222333444-eu-west-1" in res.output
        assert "Created S3 bucket" in res.output


def test_cli_bootstrap_prompt_abort(
    test_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(test_workspace)
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

        res = runner.invoke(app, ["bootstrap"], input="n\n")
        assert res.exit_code == 0
        assert "Bootstrap aborted by user." in res.output
