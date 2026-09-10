"""Configuration warning compilers and diagnostic checks."""

from __future__ import annotations

from lza_workbench.configuration.inspection.models import (
    CodeCommitConfigurationRepositoryStatus,
    CodeConnectionConfigurationRepositoryStatus,
    ConfigurationPipelineStatus,
    ConfigurationRepositoryStatus,
    ConfigurationWorkspaceStatus,
    LocalGitStatus,
    S3ConfigurationRepositoryStatus,
)


def _compile_workspace_warnings(workspace: ConfigurationWorkspaceStatus) -> list[str]:
    """Compile warnings from local workspace observations."""
    warnings: list[str] = []
    if not workspace.config_dir_exists:
        warnings.append(
            "Local configuration directory is missing. "
            "Run 'lza config init' or 'lza config pull' to initialize it."
        )
    if workspace.drifted_fields:
        warnings.append(
            "Workspace settings changed since template initialization "
            f"({', '.join(workspace.drifted_fields)}). "
            "Run 'lza config init --force' to re-apply the template."
        )
    return warnings


def _compile_local_git_warnings(local_git: LocalGitStatus) -> list[str]:
    """Compile warnings from local Git observations."""
    warnings: list[str] = []
    if local_git.working_tree and local_git.working_tree.has_uncommitted:
        warnings.append(
            f"Local configuration contains {local_git.working_tree.uncommitted_count} uncommitted "
            "change(s). Commit or stash your changes before pushing."
        )
    if local_git.sync_status and local_git.sync_status.status == "Behind":
        warnings.append(
            f"Local configuration is behind remote repository by {local_git.sync_status.behind} "
            "commit(s). Run 'lza config pull' to synchronize."
        )
    elif local_git.sync_status and local_git.sync_status.status == "Diverged":
        warnings.append(
            f"Local configuration has diverged from remote ({local_git.sync_status.ahead} ahead, "
            f"{local_git.sync_status.behind} behind). Reconcile Git history before pushing."
        )
    return warnings


def _compile_s3_repository_warnings(repository: S3ConfigurationRepositoryStatus) -> list[str]:
    """Compile warnings from an S3 configuration repository."""
    label = f" '{repository.bucket}'" if repository.bucket else ""
    if repository.bucket_exists is False:
        return [f"Configured S3 bucket{label} does not exist."]
    if repository.bucket_accessible is False:
        return [f"Access denied or connection failure to configured S3 bucket{label}."]
    if repository.bucket_exists is True and repository.object_exists is False:
        return [
            f"Configuration archive is not present in S3 bucket{label}. "
            "Run 'lza config push' to upload local configuration."
        ]
    return []


def _compile_codecommit_repository_warnings(
    repository: CodeCommitConfigurationRepositoryStatus,
) -> list[str]:
    """Compile warnings from a CodeCommit configuration repository."""
    if repository.exists is False:
        return ["Configured CodeCommit repository does not exist."]
    if repository.accessible is False:
        return ["Access denied or connection failure to CodeCommit repository."]
    if repository.exists is True and repository.branch_exists is False:
        return [
            "Configured branch does not exist in CodeCommit repository. "
            "Run 'lza config push' to push branch."
        ]
    return []


def _compile_codeconnection_repository_warnings(
    repository: CodeConnectionConfigurationRepositoryStatus,
) -> list[str]:
    """Compile warnings from a CodeConnection configuration repository."""
    if repository.status == "PENDING":
        return ["CodeConnection is in PENDING status. Complete the handshake in the AWS Console."]
    if repository.status in {"ERROR", "NOT_FOUND", "INACCESSIBLE"}:
        return [f"CodeConnection issue detected (Status: {repository.status})."]
    return []


def _compile_repository_warnings(repository: ConfigurationRepositoryStatus) -> list[str]:
    """Compile warnings from the configured remote repository."""
    if isinstance(repository, S3ConfigurationRepositoryStatus):
        return _compile_s3_repository_warnings(repository)
    if isinstance(repository, CodeCommitConfigurationRepositoryStatus):
        return _compile_codecommit_repository_warnings(repository)
    if isinstance(repository, CodeConnectionConfigurationRepositoryStatus):
        return _compile_codeconnection_repository_warnings(repository)
    return []


def _compile_pipeline_warnings(pipeline: ConfigurationPipelineStatus) -> list[str]:
    """Compile warnings from the latest configuration pipeline execution."""
    if pipeline.status == "Failed":
        detail = (
            f" (Stage: '{pipeline.failed_stage}', Action: '{pipeline.failed_action}')"
            if pipeline.failed_stage and pipeline.failed_action
            else f" (Stage: '{pipeline.failed_stage}')"
            if pipeline.failed_stage
            else ""
        )
        return [f"Latest execution of configuration pipeline '{pipeline.name}' failed{detail}."]
    if pipeline.status == "Cancelled":
        return [f"Latest execution of configuration pipeline '{pipeline.name}' was cancelled."]
    return []


def compile_configuration_warnings(
    *,
    workspace: ConfigurationWorkspaceStatus,
    local_git: LocalGitStatus,
    repository: ConfigurationRepositoryStatus,
    pipeline: ConfigurationPipelineStatus,
) -> tuple[str, ...]:
    """Interpret configuration observations into actionable warnings."""
    warnings = _compile_workspace_warnings(workspace)
    warnings.extend(_compile_local_git_warnings(local_git))
    warnings.extend(_compile_repository_warnings(repository))
    warnings.extend(_compile_pipeline_warnings(pipeline))
    return tuple(warnings)


__all__ = [
    "compile_configuration_warnings",
]
