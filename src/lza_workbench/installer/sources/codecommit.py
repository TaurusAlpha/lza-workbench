"""CodeCommit installer source provider."""

from __future__ import annotations

from typing import Any

from lza_workbench.infrastructure.aws.codecommit import inspect_codecommit_repository
from lza_workbench.installer.source import (
    prepare_codecommit_source_plan,
)


class CodeCommitInstallerSourceProvider:
    """CodeCommit source provider for LZA installer pipeline."""

    def __init__(
        self,
        *,
        repository_name: str,
        branch_name: str,
        region: str = "us-east-1",
        codecommit_client: Any = None,
    ) -> None:
        self.repository_name = repository_name
        self.branch_name = branch_name
        self.region = region
        self.codecommit_client = codecommit_client

    def inspect_prerequisites(self) -> dict[str, Any]:
        """Inspect CodeCommit repository status."""
        observation = None
        if self.codecommit_client:
            observation = inspect_codecommit_repository(
                self.codecommit_client,
                self.repository_name,
                branch=self.branch_name,
            )

        plan = prepare_codecommit_source_plan(
            repository_type="codecommit",
            repository_name=self.repository_name,
            branch_name=self.branch_name,
            version_ref=self.branch_name,
            region=self.region,
            observation=observation,
        )

        return {
            "repository_name": self.repository_name,
            "branch_name": self.branch_name,
            "status": plan.status,
            "creation_required": plan.creation_required,
            "sync_required": plan.sync_required,
            "actions": plan.actions,
        }

    def validate_readiness(self) -> bool:
        """Validate if the repository exists and branch exists."""
        if not self.codecommit_client:
            return True
        obs = inspect_codecommit_repository(
            self.codecommit_client,
            self.repository_name,
            branch=self.branch_name,
        )
        return obs.exists and obs.branch_exists


__all__ = ["CodeCommitInstallerSourceProvider"]
