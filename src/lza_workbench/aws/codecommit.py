"""Thin AWS CodeCommit service adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from lza_workbench.aws.client_factory import AwsClientFactory
from lza_workbench.errors import LzaError


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
    repository_name: str,
    branch_name: str,
    factory: AwsClientFactory | None = None,
    client: Any | None = None,
) -> CodeCommitRepositoryStatus:
    """Inspect a resolved CodeCommit repository and branch without feature policy."""
    cc_client = (
        client if client is not None else (factory.get_client("codecommit") if factory else None)
    )
    if cc_client is None:
        return CodeCommitRepositoryStatus(
            repository_name, branch_name, False, False, False, "No AWS client available"
        )
    try:
        cc_client.get_repository(repositoryName=repository_name)
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
        cc_client.get_branch(repositoryName=repository_name, branchName=branch_name)
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
    repository_name: str,
    description: str,
    factory: AwsClientFactory | None = None,
    client: Any | None = None,
) -> None:
    """Create a resolved CodeCommit repository only when it does not exist."""
    cc_client = (
        client if client is not None else (factory.get_client("codecommit") if factory else None)
    )
    if cc_client is None:
        raise LzaError("AWS CodeCommit client is not available")
    try:
        cc_client.get_repository(repositoryName=repository_name)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code", "") in {
            "RepositoryDoesNotExistException",
            "404",
        }:
            cc_client.create_repository(
                repositoryName=repository_name, repositoryDescription=description
            )
        else:
            raise


def inspect_codecommit_config_repository(**kwargs: Any) -> dict[str, Any]:
    """Return generic repository observations in the configuration status shape."""
    status = inspect_codecommit_repository(**kwargs)
    return {
        "exists": status.exists,
        "accessible": status.accessible,
        "branch_exists": status.branch_exists,
        "error": status.error,
        "not_found": status.not_found,
    }


__all__ = [
    "CodeCommitRepositoryStatus",
    "ensure_codecommit_repository",
    "inspect_codecommit_config_repository",
    "inspect_codecommit_repository",
]
