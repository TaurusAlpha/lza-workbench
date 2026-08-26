"""Configuration status interpretation and remediation rules."""

from __future__ import annotations

from lza_workbench.configuration.git import GitRemoteSyncStatus, GitWorkingTreeStatus


def compile_configuration_warnings(
    *,
    config_dir_exists: bool,
    drifted_fields: tuple[str, ...],
    git_working_tree: GitWorkingTreeStatus | None,
    git_sync_status: GitRemoteSyncStatus | None,
    repository_type: str,
    s3_bucket_name: str | None = None,
    s3_bucket_exists: bool | None,
    s3_bucket_accessible: bool | None,
    s3_object_exists: bool | None,
    codecommit_exists: bool | None,
    codecommit_accessible: bool | None,
    codecommit_branch_exists: bool | None,
    codeconnection_status: str | None,
    pipeline_name: str,
    pipeline_status: str | None,
    pipeline_failed_stage: str | None,
    pipeline_failed_action: str | None,
) -> tuple[str, ...]:
    """Interpret configuration observations into actionable warnings."""
    warnings: list[str] = []
    if not config_dir_exists:
        warnings.append(
            "Local configuration directory is missing. "
            "Run 'lza config init' or 'lza config pull' to initialize it."
        )
    if drifted_fields:
        warnings.append(
            "Workspace settings changed since template initialization "
            f"({', '.join(drifted_fields)}). "
            "Run 'lza config init --force' to re-apply the template."
        )
    if git_working_tree and git_working_tree.has_uncommitted:
        warnings.append(
            f"Local configuration contains {git_working_tree.uncommitted_count} uncommitted "
            "change(s). Commit or stash your changes before pushing."
        )
    if git_sync_status and git_sync_status.status == "Behind":
        warnings.append(
            f"Local configuration is behind remote repository by {git_sync_status.behind} "
            "commit(s). Run 'lza config pull' to synchronize."
        )
    elif git_sync_status and git_sync_status.status == "Diverged":
        warnings.append(
            f"Local configuration has diverged from remote ({git_sync_status.ahead} ahead, "
            f"{git_sync_status.behind} behind). Reconcile Git history before pushing."
        )
    if repository_type == "s3":
        label = f" '{s3_bucket_name}'" if s3_bucket_name else ""
        if s3_bucket_exists is False:
            warnings.append(f"Configured S3 bucket{label} does not exist.")
        elif s3_bucket_accessible is False:
            warnings.append(f"Access denied or connection failure to configured S3 bucket{label}.")
        elif s3_bucket_exists is True and s3_object_exists is False:
            warnings.append(
                f"Configuration archive is not present in S3 bucket{label}. "
                "Run 'lza config push' to upload local configuration."
            )
    elif repository_type == "codecommit":
        if codecommit_exists is False:
            warnings.append("Configured CodeCommit repository does not exist.")
        elif codecommit_accessible is False:
            warnings.append("Access denied or connection failure to CodeCommit repository.")
        elif codecommit_exists is True and codecommit_branch_exists is False:
            warnings.append(
                "Configured branch does not exist in CodeCommit repository. "
                "Run 'lza config push' to push branch."
            )
    elif repository_type == "codeconnection":
        if codeconnection_status == "PENDING":
            warnings.append(
                "CodeConnection is in PENDING status. Complete the handshake in the AWS Console."
            )
        elif codeconnection_status in {"ERROR", "NOT_FOUND", "INACCESSIBLE"}:
            warnings.append(f"CodeConnection issue detected (Status: {codeconnection_status}).")
    if pipeline_status == "Failed":
        detail = (
            f" (Stage: '{pipeline_failed_stage}', Action: '{pipeline_failed_action}')"
            if pipeline_failed_stage and pipeline_failed_action
            else f" (Stage: '{pipeline_failed_stage}')"
            if pipeline_failed_stage
            else ""
        )
        warnings.append(
            f"Latest execution of configuration pipeline '{pipeline_name}' failed{detail}."
        )
    elif pipeline_status == "Cancelled":
        warnings.append(
            f"Latest execution of configuration pipeline '{pipeline_name}' was cancelled."
        )
    return tuple(warnings)
