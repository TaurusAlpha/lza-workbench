"""Tests for Secrets Manager AWS adapter."""

from __future__ import annotations

from unittest.mock import MagicMock

from botocore.exceptions import ClientError

from lza_workbench.aws.secrets_manager import (
    create_or_update_secret,
    inspect_secret_details,
    inspect_secret_exists,
)


def test_inspect_secret_exists_true() -> None:
    client = MagicMock()
    client.describe_secret.return_value = {"ARN": "arn:aws:secretsmanager:..."}

    exists, err = inspect_secret_exists("test-secret", client=client)
    assert exists is True
    assert err is None


def test_inspect_secret_exists_false_404() -> None:
    client = MagicMock()
    client.describe_secret.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException"}}, "DescribeSecret"
    )

    exists, err = inspect_secret_exists("test-secret", client=client)
    assert exists is False
    assert err is None


def test_inspect_secret_details_accessible() -> None:
    client = MagicMock()
    client.describe_secret.return_value = {"ARN": "arn:aws:secretsmanager:..."}
    client.get_secret_value.return_value = {"SecretString": "ghp_secret_token"}

    details = inspect_secret_details("accelerator/github-token", client=client)
    assert details["exists"] is True
    assert details["accessible"] is True
    assert details["value"] == "ghp_secret_token"
    assert details["error"] is None


def test_inspect_secret_details_missing() -> None:
    client = MagicMock()
    client.describe_secret.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException"}}, "DescribeSecret"
    )

    details = inspect_secret_details("accelerator/github-token", client=client)
    assert details["exists"] is False
    assert details["accessible"] is False
    assert details["value"] is None


def test_inspect_secret_details_access_denied() -> None:
    client = MagicMock()
    client.describe_secret.return_value = {"ARN": "arn:aws:secretsmanager:..."}
    client.get_secret_value.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException"}}, "GetSecretValue"
    )

    details = inspect_secret_details("accelerator/github-token", client=client)
    assert details["exists"] is True
    assert details["accessible"] is False
    assert "Access denied" in details["error"]


def test_create_or_update_secret_creates_when_missing() -> None:
    client = MagicMock()
    client.describe_secret.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException"}}, "DescribeSecret"
    )

    create_or_update_secret("accelerator/github-token", "ghp_val", client=client)
    client.create_secret.assert_called_once_with(
        Name="accelerator/github-token",
        SecretString="ghp_val",
        Description="LZA Workbench Secret",
    )


def test_create_or_update_secret_updates_when_existing() -> None:
    client = MagicMock()
    client.describe_secret.return_value = {"ARN": "arn:aws:secretsmanager:..."}

    create_or_update_secret("accelerator/github-token", "ghp_new_val", client=client)
    client.put_secret_value.assert_called_once_with(
        SecretId="accelerator/github-token",
        SecretString="ghp_new_val",
    )
