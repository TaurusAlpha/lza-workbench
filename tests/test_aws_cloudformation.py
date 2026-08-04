"""Tests for AWS CodeCommit and CloudFormation inspection modules."""

from __future__ import annotations

from unittest.mock import MagicMock

from botocore.exceptions import ClientError

from lza_workbench.aws.cloudformation import inspect_cloudformation_stack


def test_inspect_cloudformation_stack_create() -> None:
    """Test CloudFormation stack inspection when stack does not exist."""
    session = MagicMock()
    client = MagicMock()
    session.client.return_value = client

    client.describe_stacks.side_effect = ClientError(
        {"Error": {"Code": "ValidationError", "Message": "Stack does not exist"}},
        "DescribeStacks",
    )

    res = inspect_cloudformation_stack(
        session=session,
        stack_name="MyStack",
        resolved_parameters={"Param1": "Val1"},
    )

    assert res.operation == "CREATE"
    assert res.stack_status is None
