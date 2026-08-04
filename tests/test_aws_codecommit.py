"""Tests for AWS CodeCommit and CloudFormation inspection modules."""

from __future__ import annotations

from unittest.mock import MagicMock

from botocore.exceptions import ClientError

from lza_workbench.aws.cloudformation import inspect_cloudformation_stack
from lza_workbench.aws.codecommit import inspect_codecommit_repository


def test_inspect_codecommit_repository_missing() -> None:
    """Test CodeCommit inspection when repository does not exist."""
    session = MagicMock()
    client = MagicMock()
    session.client.return_value = client

    client.get_repository.side_effect = ClientError(
        {"Error": {"Code": "RepositoryDoesNotExistException"}}, "GetRepository"
    )

    res = inspect_codecommit_repository(
        session=session,
        repository_type="codecommit",
        repository_name="my-repo",
        branch_name="main",
        lza_version="v1.16.0",
        region="us-east-1",
    )

    assert res.status == "MISSING"
    assert res.creation_required is True
    assert res.sync_required is True
    assert any("Create CodeCommit repository" in action for action in res.actions)


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
