"""Installer source repository inspection and access verification."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lza_workbench.errors import LzaError
from lza_workbench.infrastructure.aws.codecommit import inspect_codecommit_repository
from lza_workbench.infrastructure.aws.s3 import inspect_s3_object
from lza_workbench.infrastructure.aws.secrets_manager import inspect_secret_exists
from lza_workbench.installer.parameters import resolve_installer_source_branch
from lza_workbench.installer.source.planning import (
    CodeCommitPlanResult,
    prepare_codecommit_source_plan,
)

if TYPE_CHECKING:
    from lza_workbench.infrastructure.aws.session import AwsClientFactory
    from lza_workbench.workspace.schema import WorkspaceConfig


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


def validate_github_repository_access(
    *,
    owner: str = "awslabs",
    repository_name: str = "landing-zone-accelerator-on-aws",
    branch: str | None = None,
    token: str | None = None,
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    """Validate that a GitHub repository (and optional branch) is accessible."""
    import urllib.error
    import urllib.request

    clean_owner = (owner or "awslabs").strip()
    clean_repo = (repository_name or "landing-zone-accelerator-on-aws").strip()
    repo_url = f"https://api.github.com/repos/{clean_owner}/{clean_repo}"

    headers = {
        "User-Agent": "LZA-Workbench",
        "Accept": "application/vnd.github+json",
    }
    if token and token.strip():
        headers["Authorization"] = f"Bearer {token.strip()}"

    req = urllib.request.Request(repo_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds):
            pass
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {
                "accessible": False,
                "error": (
                    f"Repository '{clean_owner}/{clean_repo}' not found or lacks access (HTTP 404)."
                ),
            }
        if exc.code == 401:
            return {
                "accessible": False,
                "error": (
                    "GitHub Personal Access Token is invalid or expired (HTTP 401 Unauthorized)."
                ),
            }
        if exc.code == 403:
            return {
                "accessible": False,
                "error": (
                    f"GitHub API access forbidden for '{clean_owner}/{clean_repo}' (HTTP 403)."
                ),
            }
        return {
            "accessible": False,
            "error": f"GitHub API returned HTTP {exc.code}: {exc.reason}",
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "accessible": False,
            "error": f"Could not connect to GitHub API: {exc}",
        }
    except Exception as exc:
        return {
            "accessible": False,
            "error": f"Unexpected error checking GitHub repository: {exc}",
        }

    if branch and branch.strip():
        clean_branch = branch.strip()
        branch_url = (
            f"https://api.github.com/repos/{clean_owner}/{clean_repo}/branches/{clean_branch}"
        )
        branch_req = urllib.request.Request(branch_url, headers=headers)
        try:
            with urllib.request.urlopen(branch_req, timeout=timeout_seconds):
                pass
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return {
                    "accessible": False,
                    "error": (
                        f"Branch '{clean_branch}' not found in repository "
                        f"'{clean_owner}/{clean_repo}' (HTTP 404)."
                    ),
                }
            return {
                "accessible": False,
                "error": (
                    f"GitHub API returned HTTP {exc.code} for branch '{clean_branch}': {exc.reason}"
                ),
            }
        except Exception as exc:
            return {
                "accessible": False,
                "error": f"Could not verify branch '{clean_branch}' on GitHub: {exc}",
            }

    return {
        "accessible": True,
        "error": None,
    }


def inspect_installer_source(
    *,
    factory: AwsClientFactory,
    config: WorkspaceConfig,
    region: str,
) -> CodeCommitPlanResult | None:
    """Validate required remote source preconditions for installer CloudFormation."""
    source = config.installer.source_code
    if source.repository_type == "codecommit":
        version_ref = resolve_installer_source_branch(
            source.repository_type, source.branch, config.lza.version
        )
        observation = inspect_codecommit_repository(
            client=factory.get_client("codecommit"),
            repository_name=source.repository_name or "aws-accelerator-codecommit",
            branch_name=source.branch or version_ref,
        )
        plan = prepare_codecommit_source_plan(
            repository_type="codecommit",
            repository_name=source.repository_name,
            branch_name=source.branch,
            version_ref=version_ref,
            region=region,
            observation=observation,
        )
        if plan.status != "INITIALIZED":
            raise LzaError(
                "CodeCommit source is a manual prerequisite: repository "
                f"'{plan.repository_name}' must contain branch '{plan.branch_name}' before "
                "installer deployment. Run 'lza installer plan' for the required source actions."
            )
        return plan

    if source.repository_type == "s3":
        inspect_s3_object(
            client=factory.get_client("s3"),
            bucket_name=source.bucket or "",
            object_key=source.key or "",
        )
    elif source.repository_type == "github":
        exists, error = inspect_secret_exists(
            client=factory.get_client("secretsmanager"),
            secret_name=source.github_secret_name,
        )
        warning = github_secret_warning(source.github_secret_name, exists, error)
        if warning:
            raise LzaError(warning)
        return None
    return None


__all__ = [
    "github_secret_warning",
    "inspect_installer_source",
    "validate_github_repository_access",
]
