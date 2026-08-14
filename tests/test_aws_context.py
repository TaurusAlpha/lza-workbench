"""Tests for shared AWS execution-context resolution."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.core.errors import LzaError
from lza_workbench.workspace.models import AwsConfig


@patch("lza_workbench.aws.context.AwsClientFactory.from_aws_config")
def test_resolver_uses_configured_profile_and_region(mock_from_config: MagicMock) -> None:
    factory = MagicMock()
    factory.validate_identity.return_value = {"account": "123456789012", "arn": "arn:test"}
    mock_from_config.return_value = factory

    context = resolve_aws_execution_context(AwsConfig(profile="selected", region="eu-west-1"))

    assert context.region == "eu-west-1"
    assert context.identity == {"account": "123456789012", "arn": "arn:test"}
    assert mock_from_config.call_args.args[0].profile == "selected"


@patch("lza_workbench.aws.context.AwsClientFactory.from_aws_config")
def test_resolver_uses_profile_override_without_losing_role(mock_from_config: MagicMock) -> None:
    factory = MagicMock()
    mock_from_config.return_value = factory

    resolve_aws_execution_context(
        AwsConfig(
            profile="workspace",
            role_arn="arn:aws:iam::123456789012:role/Lza",
            region="eu-west-1",
        ),
        profile_override="override",
        validate_identity=False,
    )

    resolved = mock_from_config.call_args.args[0]
    assert resolved.profile == "override"
    assert resolved.role_arn == "arn:aws:iam::123456789012:role/Lza"


@patch("lza_workbench.aws.context.AwsClientFactory.from_aws_config")
def test_mutating_resolver_rejects_unexpected_account(mock_from_config: MagicMock) -> None:
    factory = MagicMock()
    factory.validate_identity.return_value = {"account": "999999999999", "arn": "arn:test"}
    mock_from_config.return_value = factory

    with pytest.raises(LzaError, match="does not match"):
        resolve_aws_execution_context(
            AwsConfig(profile="selected", account_id="123456789012"),
            require_identity=True,
            require_expected_account=True,
        )
