"""Installer source precondition planning."""

from __future__ import annotations

from dataclasses import dataclass, field

from lza_workbench.aws.codecommit import CodeCommitRepositoryStatus


@dataclass(frozen=True)
class CodeCommitPlanResult:
    repository_name: str
    branch_name: str
    status: str
    creation_required: bool
    sync_required: bool
    official_repo_url: str
    official_version_ref: str
    actions: list[str] = field(default_factory=list)


def prepare_codecommit_source_plan(
    *,
    repository_type: str,
    repository_name: str | None,
    branch_name: str | None,
    version_ref: str,
    region: str,
    observation: CodeCommitRepositoryStatus | None,
) -> CodeCommitPlanResult:
    """Apply LZA installer source rules to generic CodeCommit observations."""
    repo_name = (repository_name or "aws-accelerator-codecommit").strip()
    branch = (branch_name or version_ref).strip()
    official_url = "https://github.com/awslabs/landing-zone-accelerator-on-aws"
    if repository_type != "codecommit":
        return CodeCommitPlanResult(
            repo_name,
            branch,
            "N/A",
            False,
            False,
            official_url,
            version_ref,
            [f"Installer source repository type is '{repository_type}'"],
        )
    actions = [
        f"Create CodeCommit repository '{repo_name}' in region '{region}'",
        f"Clone official LZA repo awslabs/landing-zone-accelerator-on-aws@{version_ref}",
        f"Push to CodeCommit repository '{repo_name}' branch '{branch}'",
    ]
    if observation is None:
        return CodeCommitPlanResult(
            repo_name, branch, "UNCHECKED", True, True, official_url, version_ref, actions
        )
    if not observation.accessible:
        return CodeCommitPlanResult(
            repo_name,
            branch,
            "INACCESSIBLE",
            False,
            False,
            official_url,
            version_ref,
            [
                f"CodeCommit inspection failed for '{repo_name}': "
                f"{observation.error or 'unknown error'}"
            ],
        )
    if not observation.exists:
        return CodeCommitPlanResult(
            repo_name, branch, "MISSING", True, True, official_url, version_ref, actions
        )
    if not observation.branch_exists:
        return CodeCommitPlanResult(
            repo_name,
            branch,
            "UNINITIALIZED",
            False,
            True,
            official_url,
            version_ref,
            [
                f"Sync from awslabs/landing-zone-accelerator-on-aws@{version_ref}",
                f"Push to CodeCommit repository '{repo_name}' branch '{branch}'",
            ],
        )
    return CodeCommitPlanResult(
        repo_name,
        branch,
        "INITIALIZED",
        False,
        False,
        official_url,
        version_ref,
        [f"No action required: repository '{repo_name}' branch '{branch}' exists."],
    )


def github_secret_warning(secret_name: str, exists: bool, error: str | None = None) -> str | None:
    """Interpret a generic secret observation using the installer prerequisite rule."""
    if error:
        return f"Secrets Manager check for '{secret_name}' failed: {error}"
    if exists:
        return None
    return (
        f"GitHub source selected, but AWS Secrets Manager secret '{secret_name}' "
        "was not found in account/region. AWS LZA requires a GitHub token stored "
        "in Secrets Manager."
    )
