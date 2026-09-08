"""Thin AWS CodeCommit service adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError


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
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        not_found = code in {"RepositoryDoesNotExistException", "404"}
        accessible = False
        return CodeCommitRepositoryStatus(
            repository_name,
            branch_name,
            False,
            accessible,
            False,
            str(exc),
            not_found,
        )
    except BotoCoreError as exc:
        return CodeCommitRepositoryStatus(
            repository_name, branch_name, False, False, False, str(exc)
        )
    try:
        client.get_branch(repositoryName=repository_name, branchName=branch_name)
        return CodeCommitRepositoryStatus(repository_name, branch_name, True, True, True)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        return CodeCommitRepositoryStatus(
            repository_name,
            branch_name,
            True,
            code == "BranchDoesNotExistException",
            False,
            str(exc),
        )
    except BotoCoreError as exc:
        return CodeCommitRepositoryStatus(
            repository_name, branch_name, True, False, False, str(exc)
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
