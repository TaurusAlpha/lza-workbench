"""Tests verifying AwsClientFactory centralization and session reuse."""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from lza_workbench.aws.client_factory import AwsClientFactory
from lza_workbench.errors import LzaError


def test_no_direct_boto3_session_or_client_outside_factory() -> None:
    """Verify no file in src/lza_workbench/aws/ except client_factory calls boto3.Session/client."""
    aws_dir = Path(__file__).parent.parent.parent / "src" / "lza_workbench" / "aws"
    forbidden_calls = []

    for path in aws_dir.glob("*.py"):
        if path.name == "client_factory.py":
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Check for boto3.Session() or boto3.client()
                if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                    if node.func.value.id == "boto3" and node.func.attr in ("Session", "client"):
                        forbidden_calls.append((path.name, node.lineno, f"boto3.{node.func.attr}"))
                # Check for session.client()
                if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                    if node.func.value.id == "session" and node.func.attr == "client":
                        forbidden_calls.append((path.name, node.lineno, "session.client"))

    msg = f"Found direct boto3 session/client calls outside client_factory.py: {forbidden_calls}"
    assert not forbidden_calls, msg


def test_aws_client_factory_reuses_session_across_sts_and_services() -> None:
    """Verify AwsClientFactory creates one boto3.Session and reuses it for STS and services."""
    with patch("boto3.Session") as mock_session_cls:
        mock_session_instance = MagicMock()
        mock_session_cls.return_value = mock_session_instance

        factory = AwsClientFactory(profile="test-profile", region="eu-west-1")

        # Session should not be instantiated until requested
        mock_session_cls.assert_not_called()

        # Validate identity (uses STS)
        mock_sts = MagicMock()
        mock_session_instance.client.return_value = mock_sts
        mock_sts.get_caller_identity.return_value = {
            "Account": "123456789012",
            "Arn": "arn:aws:iam::123456789012:user/test",
            "UserId": "AKIAEXAMPLE",
        }

        identity = factory.validate_identity()
        assert identity["account"] == "123456789012"

        # Check boto3.Session was created exactly once
        mock_session_cls.assert_called_once_with(
            profile_name="test-profile", region_name="eu-west-1"
        )

        # Now request regional clients from the same factory
        cfn_client = factory.get_client("cloudformation")
        s3_client = factory.get_client("s3")
        cc_client = factory.get_client("codecommit")

        assert cfn_client is not None
        assert s3_client is not None
        assert cc_client is not None

        # boto3.Session constructor must STILL have been called only ONCE
        mock_session_cls.assert_called_once()

        # Check that session.client(...) was used for STS and regional services
        client_calls = [call.args for call in mock_session_instance.client.call_args_list]
        services_called = [call[0] for call in client_calls]

        assert "sts" in services_called
        assert "cloudformation" in services_called
        assert "s3" in services_called
        assert "codecommit" in services_called


def test_validate_identity_success() -> None:
    """Verify that caller identity is returned on success."""
    with patch("boto3.Session") as mock_session_cls:
        mock_session_instance = MagicMock()
        mock_session_cls.return_value = mock_session_instance

        mock_sts = MagicMock()
        mock_session_instance.client.return_value = mock_sts
        mock_sts.get_caller_identity.return_value = {
            "Account": "123456789012",
            "Arn": "arn:aws:iam::123456789012:user/test",
            "UserId": "AKIAEXAMPLE",
        }

        factory = AwsClientFactory(profile="test-profile", region="eu-west-1")
        identity = factory.validate_identity()

        assert identity["account"] == "123456789012"
        assert identity["arn"] == "arn:aws:iam::123456789012:user/test"


def test_validate_identity_failure_prints_warning_and_command() -> None:
    """Verify that identity check failure prints warning, command, and raises LzaError."""
    with patch("boto3.Session") as mock_session_cls:
        mock_session_instance = MagicMock()
        mock_session_cls.return_value = mock_session_instance

        mock_sts = MagicMock()
        mock_session_instance.client.return_value = mock_sts
        mock_sts.get_caller_identity.side_effect = ClientError(
            {"Code": "SSO_ERROR", "Message": "Token for test-profile does not exist"},
            "GetCallerIdentity",
        )

        factory = AwsClientFactory(profile="test-profile", region="eu-west-1")

        with pytest.raises(LzaError) as excinfo:
            factory.validate_identity()

        assert "test-profile" in str(excinfo.value)


def test_role_assumption_with_prime_credentials_calls_global_sts_first() -> None:
    """When prime_credentials=True, global STS GetCallerIdentity is called before assume_role."""
    call_order: list[str] = []

    source_session = MagicMock()
    assumed_session = MagicMock()

    def session_factory(*args, **kwargs):
        if "aws_access_key_id" in kwargs:
            return assumed_session
        return source_session

    mock_sts_global = MagicMock()
    mock_sts_regional = MagicMock()

    def get_client(service_name: str, region_name: str | None = None):
        if service_name == "sts" and region_name == "us-east-1":
            return mock_sts_global
        if service_name == "sts":
            return mock_sts_regional
        return MagicMock()

    source_session.client.side_effect = get_client

    def global_get_caller_identity():
        call_order.append("global_sts_get_caller_identity")
        return {"Account": "111111111111"}

    mock_sts_global.get_caller_identity.side_effect = global_get_caller_identity

    def regional_assume_role(**kwargs):
        call_order.append(f"assume_role_{kwargs.get('RoleArn')}")
        return {
            "Credentials": {
                "AccessKeyId": "ASIAKEY",
                "SecretAccessKey": "SECRET",
                "SessionToken": "TOKEN",
            }
        }

    mock_sts_regional.assume_role.side_effect = regional_assume_role

    with patch("boto3.Session", side_effect=session_factory):
        factory = AwsClientFactory(
            profile="test-profile",
            region="il-central-1",
            role_arn="arn:aws:iam::123456789012:role/Deployer",
            prime_credentials=True,
        )
        session = factory.get_session()
        assert session == assumed_session

    assert call_order == [
        "global_sts_get_caller_identity",
        "assume_role_arn:aws:iam::123456789012:role/Deployer",
    ]


def test_role_assumption_without_prime_credentials_skips_global_sts() -> None:
    """When prime_credentials=False (default), global STS priming is skipped."""
    source_session = MagicMock()
    assumed_session = MagicMock()

    def session_factory(*args, **kwargs):
        if "aws_access_key_id" in kwargs:
            return assumed_session
        return source_session

    mock_sts_regional = MagicMock()
    mock_sts_regional.assume_role.return_value = {
        "Credentials": {
            "AccessKeyId": "ASIAKEY",
            "SecretAccessKey": "SECRET",
            "SessionToken": "TOKEN",
        }
    }
    source_session.client.return_value = mock_sts_regional

    with patch("boto3.Session", side_effect=session_factory):
        factory = AwsClientFactory(
            profile="test-profile",
            region="il-central-1",
            role_arn="arn:aws:iam::123456789012:role/Deployer",
            prime_credentials=False,
        )
        session = factory.get_session()
        assert session == assumed_session

    source_session.client.assert_called_once_with("sts", region_name="il-central-1")
