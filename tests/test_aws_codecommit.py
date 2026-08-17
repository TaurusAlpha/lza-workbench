"""Tests for AWS CodeCommit and CloudFormation inspection modules."""

from __future__ import annotations

from unittest.mock import MagicMock

from botocore.exceptions import ClientError

from lza_workbench.aws.cloudformation import inspect_cloudformation_stack
from lza_workbench.aws.codecommit import inspect_codecommit_repository
from lza_workbench.aws.s3 import inspect_s3_installer_source


def test_inspect_codecommit_repository_missing() -> None:
    """Test CodeCommit inspection when repository does not exist."""
    client = MagicMock()

    client.get_repository.side_effect = ClientError(
        {"Error": {"Code": "RepositoryDoesNotExistException"}}, "GetRepository"
    )

    res = inspect_codecommit_repository(
        client=client,
        repository_type="codecommit",
        repository_name="my-repo",
        branch_name="main",
        version_ref="release/v1.16.0",
        region="us-east-1",
    )

    assert res.status == "MISSING"
    assert res.creation_required is True
    assert res.sync_required is True
    assert any("Create CodeCommit repository" in action for action in res.actions)


def test_inspect_cloudformation_stack_create() -> None:
    """Test CloudFormation stack inspection when stack does not exist."""
    client = MagicMock()

    client.describe_stacks.side_effect = ClientError(
        {"Error": {"Code": "ValidationError", "Message": "Stack does not exist"}},
        "DescribeStacks",
    )

    res = inspect_cloudformation_stack(
        client=client,
        stack_name="MyStack",
        resolved_parameters={"Param1": "Val1"},
    )

    assert res.operation == "CREATE"
    assert res.stack_status is None


def test_inspect_s3_installer_source_uses_configured_bucket_and_key() -> None:
    """Installer source inspection must not substitute a generated bucket or key."""
    client = MagicMock()

    inspect_s3_installer_source(
        client=client,
        bucket_name="configured-installer-source",
        object_key="releases/v1.16.0/source.zip",
    )

    client.head_object.assert_called_once_with(
        Bucket="configured-installer-source", Key="releases/v1.16.0/source.zip"
    )


def test_inspect_codecommit_branch_exists() -> None:
    """When repo and branch both exist, status is INITIALIZED."""
    client = MagicMock()
    client.get_repository.return_value = {"repositoryMetadata": {}}
    client.get_branch.return_value = {"branch": {"branchName": "release/v1.16.0"}}

    res = inspect_codecommit_repository(
        client=client,
        repository_type="codecommit",
        repository_name="my-repo",
        branch_name="release/v1.16.0",
        version_ref="release/v1.16.0",
        region="us-east-1",
    )

    assert res.status == "INITIALIZED"
    assert res.creation_required is False
    assert res.sync_required is False


def test_inspect_codecommit_branch_missing() -> None:
    """When repo exists but branch does not, status is UNINITIALIZED."""
    client = MagicMock()
    client.get_repository.return_value = {"repositoryMetadata": {}}
    client.get_branch.side_effect = ClientError(
        {"Error": {"Code": "BranchDoesNotExistException"}}, "GetBranch"
    )

    res = inspect_codecommit_repository(
        client=client,
        repository_type="codecommit",
        repository_name="my-repo",
        branch_name="release/v1.16.0",
        version_ref="release/v1.16.0",
        region="us-east-1",
    )

    assert res.status == "UNINITIALIZED"
    assert res.creation_required is False
    assert res.sync_required is True


def test_inspect_codecommit_branch_access_denied_fails_closed() -> None:
    """When branch lookup gets AccessDenied, status must be INACCESSIBLE, not INITIALIZED."""
    client = MagicMock()
    client.get_repository.return_value = {"repositoryMetadata": {}}
    client.get_branch.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "Not authorized"}}, "GetBranch"
    )

    res = inspect_codecommit_repository(
        client=client,
        repository_type="codecommit",
        repository_name="my-repo",
        branch_name="release/v1.16.0",
        version_ref="release/v1.16.0",
        region="us-east-1",
    )

    assert res.status == "INACCESSIBLE"
    assert res.creation_required is False
    assert res.sync_required is False
    assert any("Access Denied" in action for action in res.actions)


def test_inspect_codecommit_branch_unexpected_error_fails_closed() -> None:
    """When branch lookup gets ThrottlingException, status must be INACCESSIBLE."""
    client = MagicMock()
    client.get_repository.return_value = {"repositoryMetadata": {}}
    client.get_branch.side_effect = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}, "GetBranch"
    )

    res = inspect_codecommit_repository(
        client=client,
        repository_type="codecommit",
        repository_name="my-repo",
        branch_name="release/v1.16.0",
        version_ref="release/v1.16.0",
        region="us-east-1",
    )

    assert res.status == "INACCESSIBLE"
    assert res.creation_required is False
    assert res.sync_required is False
    assert any("Unexpected CodeCommit error" in action for action in res.actions)

