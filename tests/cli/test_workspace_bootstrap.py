"""Tests for workspace bootstrap CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from typer.testing import CliRunner

from lza_workbench.cli.main import app
from lza_workbench.workflows.workspace_init import init_workspace_workflow

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
        mock_cc = MagicMock()
        mock_cc.get_repository.side_effect = ClientError(
            {"Error": {"Code": "RepositoryDoesNotExistException"}},
            "GetRepository",
        )

        def client_factory(service: str):
            return mock_s3 if service == "s3" else mock_cc

        mock_client.side_effect = client_factory

        res = runner.invoke(app, ["bootstrap", "--force"])
        assert res.exit_code == 0
        assert "ready" in res.output
        assert "s3-lza-workbench-assets-111222333444-eu-west-1" in res.output
        assert "Created S3 bucket" in res.output
        assert "Created CodeCommit repository" in res.output


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
        mock_cc = MagicMock()
        mock_cc.get_repository.side_effect = ClientError(
            {"Error": {"Code": "RepositoryDoesNotExistException"}},
            "GetRepository",
        )

        def client_factory(service: str):
            return mock_s3 if service == "s3" else mock_cc

        mock_client.side_effect = client_factory

        res = runner.invoke(app, ["bootstrap"], input="n\n")
        assert res.exit_code == 0
        assert "Bootstrap aborted by user." in res.output

