"""Thin AWS CodeCommit service adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from botocore.exceptions import ClientError

from lza_workbench.aws.errors import classify_aws_error


@dataclass(frozen=True)
class CodeCommitRepositoryStatus:
    """Observed CodeCommit repository and branch availability."""

    repository_name: str
    branch_name: str
    exists: bool
    accessible: bool
    branch_exists: bool
    error: str | None = None
    not_found: bool = False


def inspect_codecommit_repository(
    *,
    client: Any,
    repository_name: str,
    branch_name: str,
) -> CodeCommitRepositoryStatus:
    """Inspect a resolved CodeCommit repository and branch without feature policy."""
    try:
        client.get_repository(repositoryName=repository_name)
    except Exception as exc:
        info = classify_aws_error(exc)
        return CodeCommitRepositoryStatus(
            repository_name,
            branch_name,
            exists=False,
            accessible=False,
            branch_exists=False,
            error=info.message,
            not_found=info.is_not_found,
        )
    try:
        client.get_branch(repositoryName=repository_name, branchName=branch_name)
        return CodeCommitRepositoryStatus(repository_name, branch_name, True, True, True)
    except Exception as exc:
        info = classify_aws_error(exc)
        branch_exists = False
        accessible = not info.is_access_denied
        err = None if info.code == "BranchDoesNotExistException" else info.message
        return CodeCommitRepositoryStatus(
            repository_name,
            branch_name,
            exists=True,
            accessible=accessible,
            branch_exists=branch_exists,
            error=err,
        )


def ensure_codecommit_repository(
    *,
    client: Any,
    repository_name: str,
    description: str,
) -> None:
    """Create a resolved CodeCommit repository only when it does not exist."""
    try:
        client.get_repository(repositoryName=repository_name)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code", "") in {
            "RepositoryDoesNotExistException",
            "404",
        }:
            client.create_repository(
                repositoryName=repository_name, repositoryDescription=description
            )
        else:
            raise


__all__ = [
    "CodeCommitRepositoryStatus",
    "ensure_codecommit_repository",
    "inspect_codecommit_repository",
]
