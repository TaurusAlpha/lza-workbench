"""GitHub installer source provider."""

from __future__ import annotations

from typing import Any

from lza_workbench.infrastructure.aws.secrets_manager import inspect_secret_details
from lza_workbench.infrastructure.github import validate_github_repository_access
from lza_workbench.installer.source import github_secret_warning


class GitHubInstallerSourceProvider:
    """GitHub source provider for LZA installer pipeline."""

    def __init__(
        self,
        *,
        owner: str = "awslabs",
        repository_name: str = "landing-zone-accelerator-on-aws",
        branch: str = "release/v1.15.5",
        secret_name: str | None = None,
        secrets_client: Any = None,
    ) -> None:
        self.owner = owner
        self.repository_name = repository_name
        self.branch = branch
        self.secret_name = secret_name or "accelerator/github-token"
        self.secrets_client = secrets_client

    def inspect_prerequisites(self) -> dict[str, Any]:
        """Inspect GitHub secret and repository access."""
        secret_obs = None
        warning = None
        if self.secrets_client:
            secret_obs = inspect_secret_details(
                client=self.secrets_client,
                secret_name=self.secret_name,
            )
            warning = github_secret_warning(self.secret_name, secret_obs.exists, secret_obs.error)

        repo_check = validate_github_repository_access(
            owner=self.owner,
            repository_name=self.repository_name,
            branch=self.branch,
        )

        return {
            "secret_name": self.secret_name,
            "secret_exists": secret_obs.exists if secret_obs else None,
            "secret_warning": warning,
            "repository_accessible": repo_check.get("accessible", False),
            "repository_error": repo_check.get("error"),
        }

    def validate_readiness(self) -> bool:
        """Validate if the repository is accessible."""
        info = self.inspect_prerequisites()
        return bool(info.get("repository_accessible", False))


__all__ = ["GitHubInstallerSourceProvider"]
