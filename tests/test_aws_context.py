"""Tests for shared AWS execution-context resolution."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.errors import LzaError


@patch("lza_workbench.aws.context.AwsClientFactory")
def test_resolver_uses_configured_profile_and_region(mock_factory_cls: MagicMock) -> None:
    factory = MagicMock()
    factory.validate_identity.return_value = {"account": "123456789012", "arn": "arn:test"}
    mock_factory_cls.return_value = factory

    context = resolve_aws_execution_context(profile="selected", region="eu-west-1")

    assert context.region == "eu-west-1"
    assert context.identity == {"account": "123456789012", "arn": "arn:test"}
    assert mock_factory_cls.call_args.kwargs["profile"] == "selected"
    assert mock_factory_cls.call_args.kwargs["region"] == "eu-west-1"


@patch("lza_workbench.aws.context.AwsClientFactory")
def test_resolver_uses_profile_override_without_losing_role(mock_factory_cls: MagicMock) -> None:
    factory = MagicMock()
    mock_factory_cls.return_value = factory

    resolve_aws_execution_context(
        profile="workspace",
        role_arn="arn:aws:iam::123456789012:role/Lza",
        region="eu-west-1",
        profile_override="override",
        validate_identity=False,
    )

    assert mock_factory_cls.call_args.kwargs["profile"] == "override"
    assert mock_factory_cls.call_args.kwargs["role_arn"] == "arn:aws:iam::123456789012:role/Lza"


@patch("lza_workbench.aws.context.AwsClientFactory")
def test_mutating_resolver_rejects_unexpected_account(mock_factory_cls: MagicMock) -> None:
    factory = MagicMock()
    factory.validate_identity.return_value = {"account": "999999999999", "arn": "arn:test"}
    mock_factory_cls.return_value = factory

    with pytest.raises(LzaError, match="does not match"):
        resolve_aws_execution_context(
            profile="selected",
            expected_account_id="123456789012",
            require_identity=True,
            require_expected_account=True,
        )


@patch("lza_workbench.aws.context.AwsClientFactory")
def test_resolver_passes_prime_credentials_flag(mock_factory_cls: MagicMock) -> None:
    factory = MagicMock()
    mock_factory_cls.return_value = factory

    resolve_aws_execution_context(
        profile="selected",
        region="eu-west-1",
        validate_identity=False,
        prime_credentials=True,
    )

    assert mock_factory_cls.call_args.kwargs["prime_credentials"] is True
