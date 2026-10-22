"""Operational health calculation and aggregation for root and detailed status."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lza_workbench.infrastructure.aws.errors import ObservationOutcome
from lza_workbench.status.summary import (
    ConfigurationRepoSummary,
    InstallerStackSummary,
    OverallHealthSummary,
    PipelineSummary,
)

if TYPE_CHECKING:
    from lza_workbench.workspace.validation import WorkspaceAssessment


def derive_installer_health(
    installer_stack: InstallerStackSummary,
    installer_pipe: PipelineSummary,
) -> str:
    """Derive operational health for the LZA installer stack and deployment pipeline."""
    # 1. Running executions
    if (
        installer_stack.status in (
            "CREATE_IN_PROGRESS",
            "UPDATE_IN_PROGRESS",
            "ROLLBACK_IN_PROGRESS",
        )
        or installer_pipe.status == "InProgress"
    ):
        return "Running"

    # 2. Operational failures
    if (
        installer_stack.status in (
            "CREATE_FAILED",
            "UPDATE_FAILED",
            "UPDATE_ROLLBACK_FAILED",
            "ROLLBACK_FAILED",
            "UPDATE_ROLLBACK_COMPLETE",
            "ROLLBACK_COMPLETE",
        )
        or installer_pipe.status in ("Failed", "Cancelled")
    ):
        return "Failed"

    # 3. Collection / verification failures
    stack_failed = (
        installer_stack.outcome in (
            ObservationOutcome.COLLECTION_FAILED,
            ObservationOutcome.ACCESS_DENIED,
            ObservationOutcome.AUTH_UNAVAILABLE,
        )
        or bool(installer_stack.error)
    )
    pipe_failed = (
        installer_pipe.outcome in (
            ObservationOutcome.COLLECTION_FAILED,
            ObservationOutcome.ACCESS_DENIED,
            ObservationOutcome.AUTH_UNAVAILABLE,
        )
        or bool(installer_pipe.error)
    )
    if stack_failed or pipe_failed:
        recorded = installer_pipe.status or installer_stack.status
        if recorded:
            return f"Attention Required (Verification Failed: Recorded {recorded})"
        return "Attention Required (Verification Failed)"

    # 4. Verified healthy
    if installer_stack.status in ("CREATE_COMPLETE", "UPDATE_COMPLETE", "IMPORT_COMPLETE"):
        if installer_pipe.status in ("Succeeded", "Not Started") or (
            installer_pipe.status is None and installer_pipe.outcome == ObservationOutcome.ABSENT
        ):
            return "Healthy"

    # 5. Incomplete / absent
    if not installer_stack.exists or installer_stack.status in (None, "NOT_DEPLOYED"):
        return "Incomplete"

    return "Attention Required"


def derive_configuration_health(
    config_repo: ConfigurationRepoSummary,
    config_pipe: PipelineSummary,
) -> str:
    """Derive operational health for remote configuration repository and pipeline."""
    # 1. Running executions
    if config_pipe.status == "InProgress":
        return "Running"

    # 2. Operational failures
    if config_pipe.status in ("Failed", "Cancelled"):
        return "Failed"

    # 3. Collection / verification failures
    pipe_failed = (
        config_pipe.outcome in (
            ObservationOutcome.COLLECTION_FAILED,
            ObservationOutcome.ACCESS_DENIED,
            ObservationOutcome.AUTH_UNAVAILABLE,
        )
        or bool(config_pipe.error)
    )
    repo_failed = (
        config_repo.outcome in (
            ObservationOutcome.COLLECTION_FAILED,
            ObservationOutcome.ACCESS_DENIED,
            ObservationOutcome.AUTH_UNAVAILABLE,
        )
        or bool(config_repo.error)
    )
    if pipe_failed or repo_failed:
        if config_pipe.status:
            return f"Attention Required (Verification Failed: Recorded {config_pipe.status})"
        return "Attention Required (Verification Failed)"

    # 4. Verified healthy
    if config_pipe.status == "Succeeded":
        if config_repo.remote_sync is not None and config_repo.remote_sync.status == "Diverged":
            return "Attention Required"
        return "Healthy"

    # 5. Incomplete / absent
    if not config_pipe.exists or config_pipe.status in (None, "Not Deployed", "Not Started"):
        return "Incomplete"

    return "Attention Required"


def derive_workspace_health(
    *,
    installer_health: str,
    configuration_health: str,
    config_repo: ConfigurationRepoSummary | None = None,
    assessment: WorkspaceAssessment | None = None,
    is_live: bool = True,
    has_recorded_state: bool = False,
) -> str:
    """Derive local workspace operational and readiness health."""
    if not is_live:
        return (
            "AWS Unavailable - Showing Last Known State"
            if has_recorded_state
            else "AWS Unavailable - No Recorded State"
        )

    if assessment is not None and not assessment.metadata_valid:
        return "Incomplete"

    if config_repo is not None and not config_repo.local_git_clean:
        return "Attention Required"

    if (
        installer_health == "Failed"
        or configuration_health == "Failed"
        or installer_health.startswith("Attention Required")
        or configuration_health.startswith("Attention Required")
        or installer_health == "Attention Required"
        or configuration_health == "Attention Required"
    ):
        return "Attention Required"

    if installer_health == "Running" or configuration_health == "Running":
        return "Running"

    if installer_health == "Incomplete" or configuration_health == "Incomplete":
        return "Incomplete"

    if installer_health == "Healthy" and configuration_health == "Healthy":
        return "Healthy"

    return "Attention Required"


def derive_overall_health(
    *,
    is_live: bool,
    installer_stack: InstallerStackSummary,
    installer_pipe: PipelineSummary,
    config_repo: ConfigurationRepoSummary,
    config_pipe: PipelineSummary,
    assessment: WorkspaceAssessment | None = None,
) -> OverallHealthSummary:
    """Derive unified health summaries for installer, configuration, and workspace."""
    if not is_live:
        inst_status = installer_pipe.status or installer_stack.status
        installer_health = f"Recorded: {inst_status}" if inst_status else "Unknown"
        config_status = config_pipe.status
        configuration_health = f"Recorded: {config_status}" if config_status else "Unknown"
        has_any_state = bool(
            inst_status
            or config_status
            or installer_pipe.execution_id
            or config_pipe.execution_id
        )
        workspace_health = derive_workspace_health(
            installer_health=installer_health,
            configuration_health=configuration_health,
            is_live=False,
            has_recorded_state=has_any_state,
        )
        return OverallHealthSummary(
            installer=installer_health,
            configuration=configuration_health,
            workspace=workspace_health,
            is_live=False,
        )

    installer_health = derive_installer_health(installer_stack, installer_pipe)
    configuration_health = derive_configuration_health(config_repo, config_pipe)
    all_live = (
        is_live
        and installer_stack.is_live
        and installer_pipe.is_live
        and config_pipe.is_live
        and (config_repo.is_live or config_repo.outcome == ObservationOutcome.NOT_COLLECTED)
    )
    workspace_health = derive_workspace_health(
        installer_health=installer_health,
        configuration_health=configuration_health,
        config_repo=config_repo,
        assessment=assessment,
        is_live=all_live,
    )

    return OverallHealthSummary(
        installer=installer_health,
        configuration=configuration_health,
        workspace=workspace_health,
        is_live=all_live,
    )


__all__ = [
    "derive_configuration_health",
    "derive_installer_health",
    "derive_overall_health",
    "derive_workspace_health",
]
