"""Prepared data for the installer plan presentation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lza_workbench.aws.cloudformation import CfnDeploymentPlanResult
from lza_workbench.aws.codecommit import CodeCommitPlanResult
from lza_workbench.workspace.schema import WorkspaceConfig


@dataclass(frozen=True)
class InstallerPlanResult:
    """All data needed to render a read-only installer deployment plan."""

    workspace_dir: Path
    config: WorkspaceConfig
    profile: str
    region: str
    aws_identity: dict[str, str] | None
    aws_error: str | None
    codecommit_plan: CodeCommitPlanResult
    cloudformation_plan: CfnDeploymentPlanResult
    dry_run: bool
    github_secret_warning: str | None = None


def prepare_installer_plan_result(
    *,
    workspace_dir: Path,
    config: WorkspaceConfig,
    region: str,
    aws_identity: dict[str, str] | None,
    aws_error: str | None,
    codecommit_plan: CodeCommitPlanResult,
    cloudformation_plan: CfnDeploymentPlanResult,
    dry_run: bool,
    github_secret_warning: str | None = None,
) -> InstallerPlanResult:
    """Collect command results into the presentation-independent plan result."""
    return InstallerPlanResult(
        workspace_dir=workspace_dir,
        config=config,
        profile=config.aws.profile or "",
        region=region,
        aws_identity=aws_identity,
        aws_error=aws_error,
        codecommit_plan=codecommit_plan,
        cloudformation_plan=cloudformation_plan,
        dry_run=dry_run,
        github_secret_warning=github_secret_warning,
    )
