"""Tests for AWS CodeCommit inspection module."""

from __future__ import annotations

from unittest.mock import MagicMock

from botocore.exceptions import ClientError

from lza_workbench.aws.codecommit import inspect_codecommit_repository


def test_inspect_codecommit_repository_missing() -> None:
    """Test CodeCommit inspection when repository does not exist."""
    client = MagicMock()
    client.get_repository.side_effect = ClientError(
        {"Error": {"Code": "RepositoryDoesNotExistException"}}, "GetRepository"
    )

    res = inspect_codecommit_repository(
        client=client,
        repository_name="my-repo",
        branch_name="main",
    )

    assert res.exists is False
    assert res.accessible is False
    assert res.not_found is True


def test_inspect_codecommit_branch_exists() -> None:
    """When repo and branch both exist, status is INITIALIZED."""
    client = MagicMock()
    client.get_repository.return_value = {"repositoryMetadata": {}}
    client.get_branch.return_value = {"branch": {"branchName": "release/v1.16.0"}}

    res = inspect_codecommit_repository(
        client=client,
        repository_name="my-repo",
        branch_name="release/v1.16.0",
    )

    assert res.exists is True
    assert res.branch_exists is True


def test_inspect_codecommit_branch_missing() -> None:
    """When repo exists but branch does not, status is UNINITIALIZED."""
    client = MagicMock()
    client.get_repository.return_value = {"repositoryMetadata": {}}
    client.get_branch.side_effect = ClientError(
        {"Error": {"Code": "BranchDoesNotExistException"}}, "GetBranch"
    )

    res = inspect_codecommit_repository(
        client=client,
        repository_name="my-repo",
        branch_name="release/v1.16.0",
    )

    assert res.exists is True
    assert res.branch_exists is False


def test_inspect_codecommit_branch_access_denied_fails_closed() -> None:
    """When branch lookup gets AccessDenied, status must be INACCESSIBLE, not INITIALIZED."""
    client = MagicMock()
    client.get_repository.return_value = {"repositoryMetadata": {}}
    client.get_branch.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "Not authorized"}}, "GetBranch"
    )

    res = inspect_codecommit_repository(
        client=client,
        repository_name="my-repo",
        branch_name="release/v1.16.0",
    )

    assert res.accessible is False


def test_inspect_codecommit_branch_unexpected_error_fails_closed() -> None:
    """When branch lookup gets ThrottlingException, status must be INACCESSIBLE."""
    client = MagicMock()
    client.get_repository.return_value = {"repositoryMetadata": {}}
    client.get_branch.side_effect = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}, "GetBranch"
    )

    res = inspect_codecommit_repository(
        client=client,
        repository_name="my-repo",
        branch_name="release/v1.16.0",
    )

    assert res.accessible is False


def test_inspect_codecommit_config_repository_missing() -> None:
    """Test inspect_codecommit_config_repository when repository does not exist."""
    from lza_workbench.aws.codecommit import inspect_codecommit_config_repository

    client = MagicMock()
    client.get_repository.side_effect = ClientError(
        {"Error": {"Code": "RepositoryDoesNotExistException"}}, "GetRepository"
    )

    res = inspect_codecommit_config_repository(
        client=client,
        repository_name="lza-config-source",
        branch_name="main",
    )

    assert res["exists"] is False
    assert res["accessible"] is False
    assert res["branch_exists"] is False
    assert res["not_found"] is True


def test_inspect_codecommit_config_repository_exists_branch_missing() -> None:
    """Test inspect_codecommit_config_repository when repository exists but branch does not."""
    from lza_workbench.aws.codecommit import inspect_codecommit_config_repository

    client = MagicMock()
    client.get_repository.return_value = {"repositoryMetadata": {}}
    client.get_branch.side_effect = ClientError(
        {"Error": {"Code": "BranchDoesNotExistException"}}, "GetBranch"
    )

    res = inspect_codecommit_config_repository(
        client=client,
        repository_name="lza-config-source",
        branch_name="main",
    )

    assert res["exists"] is True
    assert res["accessible"] is True
    assert res["branch_exists"] is False


def test_inspect_codecommit_config_repository_exists_branch_exists() -> None:
    """Test inspect_codecommit_config_repository when repository and branch both exist."""
    from lza_workbench.aws.codecommit import inspect_codecommit_config_repository

    client = MagicMock()
    client.get_repository.return_value = {"repositoryMetadata": {}}
    client.get_branch.return_value = {"branch": {"branchName": "main"}}

    res = inspect_codecommit_config_repository(
        client=client,
        repository_name="lza-config-source",
        branch_name="main",
    )

    assert res["exists"] is True
    assert res["accessible"] is True
    assert res["branch_exists"] is True
