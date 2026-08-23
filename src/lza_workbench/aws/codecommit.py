"""AWS CodeCommit integration utilities for LZA installer source management."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from lza_workbench.aws.client_factory import AwsClientFactory
from lza_workbench.errors import LzaError


@dataclass
class CodeCommitPlanResult:
    """Result of CodeCommit repository planning inspection."""

    repository_name: str
    branch_name: str
    status: str  # MISSING, UNINITIALIZED, INITIALIZED, INACCESSIBLE, UNCHECKED, N/A
    creation_required: bool
    sync_required: bool
    official_repo_url: str
    official_version_ref: str
    actions: list[str] = field(default_factory=list)


def inspect_codecommit_repository(
    *,
    factory: AwsClientFactory | None = None,
    client: Any | None = None,
    repository_type: str,
    repository_name: str | None,
    branch_name: str | None,
    version_ref: str,
    region: str,
) -> CodeCommitPlanResult:
    """Inspect CodeCommit repository state without mutating AWS resources."""
    repo_name = (repository_name or "aws-accelerator-codecommit").strip()
    resolved_version_ref = (version_ref or "").strip()
    resolved_branch = (branch_name or resolved_version_ref).strip()
    official_repo_url = "https://github.com/awslabs/landing-zone-accelerator-on-aws"

    if repository_type != "codecommit":
        return CodeCommitPlanResult(
            repository_name=repo_name,
            branch_name=resolved_branch,
            status="N/A",
            creation_required=False,
            sync_required=False,
            official_repo_url=official_repo_url,
            official_version_ref=resolved_version_ref,
            actions=[f"Installer source repository type is '{repository_type}'"],
        )

    if not factory and not client:
        return CodeCommitPlanResult(
            repository_name=repo_name,
            branch_name=resolved_branch,
            status="UNCHECKED",
            creation_required=True,
            sync_required=True,
            official_repo_url=official_repo_url,
            official_version_ref=resolved_version_ref,
            actions=[
                f"Create CodeCommit repository '{repo_name}' in region '{region}'",
                (
                    "Clone official LZA repo "
                    f"awslabs/landing-zone-accelerator-on-aws@{resolved_version_ref}"
                ),
                f"Push to CodeCommit repository '{repo_name}' branch '{resolved_branch}'",
            ],
        )

    try:
        cc_client = client if client is not None else factory.get_client("codecommit")  # type: ignore[union-attr]
        repo_res = cc_client.get_repository(repositoryName=repo_name)
        _ = repo_res.get("repositoryMetadata", {})

        try:
            cc_client.get_branch(repositoryName=repo_name, branchName=resolved_branch)
            status = "INITIALIZED"
            creation_req = False
            sync_req = False
            actions = [
                f"No action required: repository '{repo_name}' branch '{resolved_branch}' exists."
            ]
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"BranchDoesNotExistException", "CommitDoesNotExistException"}:
                status = "UNINITIALIZED"
                creation_req = False
                sync_req = True
                actions = [
                    f"Sync from awslabs/landing-zone-accelerator-on-aws@{resolved_version_ref}",
                    f"Push to CodeCommit repository '{repo_name}' branch '{resolved_branch}'",
                ]
            elif code in {"AccessDeniedException", "403"}:
                status = "INACCESSIBLE"
                creation_req = False
                sync_req = False
                actions = [
                    f"AWS Access Denied checking branch '{resolved_branch}' in "
                    f"CodeCommit repository '{repo_name}': {exc}"
                ]
            else:
                status = "INACCESSIBLE"
                creation_req = False
                sync_req = False
                actions = [
                    f"Unexpected CodeCommit error checking branch '{resolved_branch}' in "
                    f"repository '{repo_name}': {exc}"
                ]
        except BotoCoreError as exc:
            status = "INACCESSIBLE"
            creation_req = False
            sync_req = False
            actions = [
                f"AWS connection failure checking branch '{resolved_branch}' in "
                f"repository '{repo_name}': {exc}"
            ]

    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"RepositoryDoesNotExistException", "404"}:
            status = "MISSING"
            creation_req = True
            sync_req = True
            actions = [
                f"Create CodeCommit repository '{repo_name}' in region '{region}'",
                (
                    "Clone official LZA repo "
                    f"awslabs/landing-zone-accelerator-on-aws@{resolved_version_ref}"
                ),
                f"Push to CodeCommit repository '{repo_name}' branch '{resolved_branch}'",
            ]
        elif code in {"AccessDeniedException", "403"}:
            status = "INACCESSIBLE"
            creation_req = False
            sync_req = False
            actions = [f"AWS Access Denied checking CodeCommit repository '{repo_name}': {exc}"]
        else:
            status = "INACCESSIBLE"
            creation_req = False
            sync_req = False
            actions = [f"CodeCommit error: {exc}"]
    except BotoCoreError as exc:
        status = "INACCESSIBLE"
        creation_req = False
        sync_req = False
        actions = [f"AWS connection failure checking CodeCommit: {exc}"]

    return CodeCommitPlanResult(
        repository_name=repo_name,
        branch_name=resolved_branch,
        status=status,
        creation_required=creation_req,
        sync_required=sync_req,
        official_repo_url=official_repo_url,
        official_version_ref=resolved_version_ref,
        actions=actions,
    )


def ensure_codecommit_repository(
    *,
    factory: AwsClientFactory | None = None,
    client: Any | None = None,
    repository_name: str,
    branch_name: str = "main",
    description: str = "LZA Installer Repository",
) -> None:
    """Ensure CodeCommit repository exists, creating it if required."""
    cc_client = (
        client if client is not None else (factory.get_client("codecommit") if factory else None)
    )
    if cc_client is None:
        raise ValueError("AWS CodeCommit client is not available")

    repo_name = (repository_name or "aws-accelerator-installer").strip()

    try:
        cc_client.get_repository(repositoryName=repo_name)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"RepositoryDoesNotExistException", "404"}:
            cc_client.create_repository(
                repositoryName=repo_name,
                repositoryDescription=description,
            )
        else:
            raise


def inspect_codecommit_config_repository(
    *,
    factory: AwsClientFactory | None = None,
    client: Any | None = None,
    repository_name: str,
    branch_name: str = "main",
) -> dict[str, Any]:
    """Inspect CodeCommit repository and branch state for configuration repository."""
    cc_client = (
        client if client is not None else (factory.get_client("codecommit") if factory else None)
    )
    if cc_client is None:
        raise ValueError("AWS CodeCommit client is not available")

    clean_repo = (repository_name or "lza-config-source").strip()
    clean_branch = (branch_name or "main").strip()

    try:
        cc_client.get_repository(repositoryName=clean_repo)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"RepositoryDoesNotExistException", "404"}:
            return {
                "exists": False,
                "accessible": False,
                "branch_exists": False,
                "error": None,
            }
        if code in {"AccessDeniedException", "403"}:
            raise LzaError(
                f"Access denied checking CodeCommit repository '{clean_repo}': {exc}"
            ) from exc
        raise LzaError(
            f"CodeCommit inspection error on repository '{clean_repo}': {exc}"
        ) from exc
    except BotoCoreError as exc:
        raise LzaError(
            f"AWS connection failure checking CodeCommit repository '{clean_repo}': {exc}"
        ) from exc

    branch_exists = False
    try:
        cc_client.get_branch(repositoryName=clean_repo, branchName=clean_branch)
        branch_exists = True
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"BranchDoesNotExistException", "CommitDoesNotExistException"}:
            branch_exists = False
        elif code in {"AccessDeniedException", "403"}:
            raise LzaError(
                f"Access denied checking branch '{clean_branch}' in "
                f"CodeCommit repository '{clean_repo}': {exc}"
            ) from exc
        else:
            raise LzaError(
                f"Error checking branch '{clean_branch}' in "
                f"CodeCommit repository '{clean_repo}': {exc}"
            ) from exc
    except BotoCoreError as exc:
        raise LzaError(
            f"AWS connection failure checking branch '{clean_branch}': {exc}"
        ) from exc

    return {
        "exists": True,
        "accessible": True,
        "branch_exists": branch_exists,
        "error": None,
    }


__all__ = [
    "CodeCommitPlanResult",
    "ensure_codecommit_repository",
    "inspect_codecommit_config_repository",
    "inspect_codecommit_repository",
]
