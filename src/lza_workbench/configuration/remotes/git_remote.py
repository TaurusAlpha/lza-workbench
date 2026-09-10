"""Git and CodeCommit configuration remote provider."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lza_workbench.configuration.git import (
    configure_codecommit_credential_helper,
    get_git_branch,
    get_git_commit,
    get_git_remote_url,
    has_uncommitted_changes,
    is_git_repository,
    pull_git_branch,
    push_git_branch,
    set_git_remote_url,
)


class GitConfigurationRemote:
    """Configuration remote backed by a Git or CodeCommit repository."""

    def __init__(
        self,
        *,
        remote_url: str,
        branch: str = "main",
        remote_name: str = "origin",
        is_codecommit: bool = False,
        aws_profile: str | None = None,
        aws_region: str = "us-east-1",
    ) -> None:
        self.remote_url = remote_url
        self.branch = branch
        self.remote_name = remote_name
        self.is_codecommit = is_codecommit
        self.aws_profile = aws_profile
        self.aws_region = aws_region

    def setup_repository(self, local_path: Path) -> None:
        """Ensure git remote is set up and credentials configured if CodeCommit."""
        current_remote = get_git_remote_url(local_path, self.remote_name)
        if current_remote != self.remote_url:
            set_git_remote_url(local_path, self.remote_name, self.remote_url)
        if self.is_codecommit and self.aws_profile:
            configure_codecommit_credential_helper(
                local_path, aws_profile=self.aws_profile
            )

    def inspect(self, local_path: Path | None = None) -> dict[str, Any]:
        """Inspect the git repository status."""
        if local_path and is_git_repository(local_path):
            return {
                "branch": get_git_branch(local_path),
                "commit": get_git_commit(local_path),
                "has_uncommitted_changes": has_uncommitted_changes(local_path),
                "remote_url": self.remote_url,
            }
        return {"remote_url": self.remote_url, "branch": self.branch}

    def push(self, local_path: Path, **kwargs: Any) -> None:
        """Push local changes to the remote Git branch."""
        self.setup_repository(local_path)
        push_git_branch(local_path, self.remote_name, self.branch)

    def pull(self, local_path: Path, **kwargs: Any) -> None:
        """Pull remote changes into local Git branch."""
        self.setup_repository(local_path)
        pull_git_branch(local_path, self.remote_name, self.branch)


__all__ = ["GitConfigurationRemote"]
