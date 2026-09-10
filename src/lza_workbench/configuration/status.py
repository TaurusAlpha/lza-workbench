"""Configuration status interpretation, inspection, and reporting workflow."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.configuration.git import (
    get_git_remote_sync_status,
    get_git_working_tree_status,
)
from lza_workbench.configuration.inspection import (
    CodeCommitConfigurationRepositoryStatus,
    CodeConnectionConfigurationRepositoryStatus,
    ConfigurationPipelineActionFailure,
    ConfigurationPipelineStatus,
    ConfigurationRepositoryStatus,
    ConfigurationStatusResult,
    ConfigurationSynchronizationStatus,
    ConfigurationWorkspaceStatus,
    GitConfigurationRepositoryStatus,
    LocalGitStatus,
    S3ConfigurationRepositoryStatus,
    inspect_configuration_pipeline,
    inspect_configuration_repository,
)
from lza_workbench.configuration.templates import capture_init_values_snapshot
from lza_workbench.configuration.warnings import compile_configuration_warnings
from lza_workbench.infrastructure.aws.session import resolve_aws_execution_context
from lza_workbench.workspace.context import load_workspace_context
from lza_workbench.workspace.schema import WorkspaceConfig, WorkspaceState
from lza_workbench.workspace.validation import WorkspaceCapability


def get_config_status_workflow(
    *,
    target_dir: Path | None = None,
    config: WorkspaceConfig | None = None,
    state: WorkspaceState | None = None,
    workspace_dir: Path | None = None,
) -> ConfigurationStatusResult:
    """Query workspace configuration and remote/pipeline status data."""
    if config is not None and workspace_dir is not None:
        resolved_workspace_dir = workspace_dir
        resolved_config = config
        resolved_state = state
        config_dir = resolved_workspace_dir / resolved_config.configuration.local_path
    else:
        ctx = load_workspace_context(
            target_dir, required_capabilities=(WorkspaceCapability.METADATA_VALID,)
        )
        resolved_workspace_dir = ctx.workspace_dir
        resolved_config = ctx.config
        resolved_state = ctx.state
        config_dir = ctx.config_dir
    yaml_files = (
        tuple(
            sorted(
                file.name
                for file in config_dir.iterdir()
                if file.is_file() and file.suffix in (".yaml", ".yml")
            )
        )
        if config_dir.exists()
        else ()
    )
    repo = resolved_config.configuration.repository

    profile = resolved_config.aws.profile or ""
    aws_context = resolve_aws_execution_context(
        profile=profile,
        region=resolved_config.aws.region,
        role_arn=resolved_config.aws.role_arn,
        expected_account_id=resolved_config.aws.account_id,
        prime_credentials=resolved_config.aws.prime_credentials,
    )
    factory = aws_context.factory
    region = aws_context.region
    aws_identity = aws_context.identity
    aws_error = aws_context.error
    account_id = aws_identity["account"] if aws_identity else "UNKNOWN_ACCOUNT"

    initialized_at = resolved_state.config_initialized_at if resolved_state else None
    template_name = resolved_state.config_template_name if resolved_state else None
    template_source = resolved_state.config_template_source if resolved_state else None
    drifted_fields: tuple[str, ...] = ()
    has_init_state = bool(
        resolved_state
        and resolved_state.config_initialized_at
        and resolved_state.config_init_values
    )
    if has_init_state and resolved_state and resolved_state.config_init_values:
        current_snapshot = capture_init_values_snapshot(resolved_config)
        saved_snapshot = resolved_state.config_init_values
        drifted_fields = tuple(
            sorted(k for k, v in current_snapshot.items() if saved_snapshot.get(k) != v)
        )

    # Git working tree and remote synchronization
    git_working_tree = get_git_working_tree_status(config_dir)
    git_sync_status = (
        get_git_remote_sync_status(config_dir, branch=repo.branch) if git_working_tree else None
    )

    workspace = ConfigurationWorkspaceStatus(
        workspace_dir=resolved_workspace_dir,
        customer_name=resolved_config.customer.name,
        lza_version=resolved_config.lza.version,
        profile=profile,
        region=region,
        aws_identity=aws_identity,
        aws_error=aws_error,
        config_dir=config_dir,
        config_dir_exists=config_dir.exists(),
        yaml_files=yaml_files,
        initialized_at=initialized_at,
        template_name=template_name,
        template_source=template_source,
        drifted_fields=drifted_fields,
    )
    local_git = LocalGitStatus(working_tree=git_working_tree, sync_status=git_sync_status)

    repository, remote_sync = inspect_configuration_repository(
        repo=repo,
        config_dir=config_dir,
        resolved_config=resolved_config,
        resolved_state=resolved_state,
        aws_identity=aws_identity,
        region=region,
        factory=factory,
        git_sync_status=git_sync_status,
    )

    pipeline = inspect_configuration_pipeline(
        resolved_config=resolved_config,
        resolved_state=resolved_state,
        aws_identity=aws_identity,
        region=region,
        account_id=account_id,
        factory=factory,
    )

    recorded_pipeline_execution_id = (
        resolved_state.config_pipeline_execution_id if resolved_state else None
    )
    synchronization = ConfigurationSynchronizationStatus(
        has_state=resolved_state is not None,
        recorded_pipeline_execution_id=recorded_pipeline_execution_id,
        uploaded_at=resolved_state.config_uploaded_at if resolved_state else None,
        downloaded_at=resolved_state.config_downloaded_at if resolved_state else None,
        artifact_etag=resolved_state.config_artifact_etag if resolved_state else None,
        artifact_version_id=resolved_state.config_artifact_version_id if resolved_state else None,
        remote_sync=remote_sync,
    )

    warnings = compile_configuration_warnings(
        workspace=workspace,
        local_git=local_git,
        repository=repository,
        pipeline=pipeline,
    )
    return ConfigurationStatusResult(
        workspace=workspace,
        local_git=local_git,
        repository=repository,
        pipeline=pipeline,
        synchronization=synchronization,
        warnings=warnings,
    )


__all__ = [
    "CodeCommitConfigurationRepositoryStatus",
    "CodeConnectionConfigurationRepositoryStatus",
    "ConfigurationPipelineActionFailure",
    "ConfigurationPipelineStatus",
    "ConfigurationRepositoryStatus",
    "ConfigurationStatusResult",
    "ConfigurationSynchronizationStatus",
    "ConfigurationWorkspaceStatus",
    "GitConfigurationRepositoryStatus",
    "LocalGitStatus",
    "S3ConfigurationRepositoryStatus",
    "compile_configuration_warnings",
    "get_config_status_workflow",
]
