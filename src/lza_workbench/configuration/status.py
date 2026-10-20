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
from lza_workbench.infrastructure.aws.session import (
    AwsExecutionContext,
    resolve_aws_execution_context,
)
from lza_workbench.workspace.context import load_workspace_context
from lza_workbench.workspace.schema import (
    CustomerEnvironmentTarget,
    WorkspaceConfig,
    WorkspaceState,
)
from lza_workbench.workspace.validation import WorkspaceCapability


def get_config_status_workflow(
    *,
    target_dir: Path | None = None,
    environment_target: CustomerEnvironmentTarget | None = None,
    config: WorkspaceConfig | None = None,
    state: WorkspaceState | None = None,
    workspace_dir: Path | None = None,
    config_dir: Path | None = None,
    aws_context: AwsExecutionContext | None = None,
) -> ConfigurationStatusResult:
    """Query workspace configuration and remote/pipeline status data."""
    if config is not None:
        resolved_workspace_dir = workspace_dir
        resolved_config = config
        resolved_target = environment_target or config.environment_target
        resolved_state = state
        resolved_config_dir = config_dir or (
            resolved_workspace_dir / resolved_config.configuration.local_path
            if resolved_workspace_dir is not None
            else None
        )
    elif environment_target is not None:
        resolved_workspace_dir = workspace_dir
        resolved_config = None
        resolved_target = environment_target
        resolved_state = state
        resolved_config_dir = config_dir
    else:
        ctx = load_workspace_context(
            target_dir, required_capabilities=(WorkspaceCapability.METADATA_VALID,)
        )
        resolved_workspace_dir = ctx.workspace_dir
        resolved_config = ctx.config
        resolved_target = ctx.environment_target
        resolved_state = ctx.state
        resolved_config_dir = config_dir or ctx.config_dir

    config_dir_exists = bool(resolved_config_dir and resolved_config_dir.exists())
    yaml_files = (
        tuple(
            sorted(
                file.name
                for file in resolved_config_dir.iterdir()
                if file.is_file() and file.suffix in (".yaml", ".yml")
            )
        )
        if resolved_config_dir is not None and config_dir_exists
        else ()
    )
    repo = resolved_target.configuration_repository

    profile = (
        (resolved_config.aws.profile or "")
        if resolved_config is not None
        else (aws_context.factory.profile or "" if aws_context is not None else "")
    )
    if aws_context is not None:
        resolved_aws = aws_context
    elif resolved_config is not None:
        resolved_aws = resolve_aws_execution_context(
            profile=profile,
            region=resolved_config.aws.region,
            role_arn=resolved_config.aws.role_arn,
            expected_account_id=resolved_config.aws.account_id,
            prime_credentials=resolved_config.aws.prime_credentials,
        )
    else:
        resolved_aws = resolve_aws_execution_context(
            region=resolved_target.region,
            expected_account_id=resolved_target.account_id,
        )
    factory = resolved_aws.factory
    region = resolved_aws.region
    aws_identity = resolved_aws.identity
    aws_error = resolved_aws.error
    account_id = aws_identity["account"] if aws_identity else "UNKNOWN_ACCOUNT"

    tmpl_state = resolved_state.configuration.template if resolved_state else None
    initialized_at = tmpl_state.initialized_at if tmpl_state else None
    template_name = tmpl_state.template_name if tmpl_state else None
    template_source = tmpl_state.template_source if tmpl_state else None
    drifted_fields: tuple[str, ...] = ()
    has_init_state = bool(
        resolved_config is not None
        and tmpl_state
        and tmpl_state.initialized_at
        and tmpl_state.init_values
    )
    if (
        has_init_state
        and resolved_config is not None
        and tmpl_state
        and tmpl_state.init_values
    ):
        current_snapshot = capture_init_values_snapshot(resolved_config)
        saved_snapshot = tmpl_state.init_values
        drifted_fields = tuple(
            sorted(k for k, v in current_snapshot.items() if saved_snapshot.get(k) != v)
        )

    # Git working tree and remote synchronization
    git_working_tree = (
        get_git_working_tree_status(resolved_config_dir)
        if resolved_config_dir is not None
        else None
    )
    git_sync_status = (
        get_git_remote_sync_status(resolved_config_dir, branch=repo.branch)
        if resolved_config_dir is not None and git_working_tree
        else None
    )

    workspace = ConfigurationWorkspaceStatus(
        workspace_dir=resolved_workspace_dir,
        customer_name=resolved_target.customer.name,
        lza_version=resolved_target.lza.version,
        profile=profile,
        region=region,
        aws_identity=aws_identity,
        aws_error=aws_error,
        config_dir=resolved_config_dir,
        config_dir_exists=config_dir_exists,
        yaml_files=yaml_files,
        initialized_at=initialized_at,
        template_name=template_name,
        template_source=template_source,
        drifted_fields=drifted_fields,
    )
    local_git = LocalGitStatus(working_tree=git_working_tree, sync_status=git_sync_status)

    repository, remote_sync = inspect_configuration_repository(
        repo=repo,
        config_dir=resolved_config_dir,
        environment_target=resolved_target,
        resolved_config=resolved_config,
        resolved_state=resolved_state,
        aws_identity=aws_identity,
        region=region,
        factory=factory,
        git_sync_status=git_sync_status,
    )

    pipeline = inspect_configuration_pipeline(
        environment_target=resolved_target,
        resolved_config=resolved_config,
        resolved_state=resolved_state,
        aws_identity=aws_identity,
        region=region,
        account_id=account_id,
        factory=factory,
    )

    recorded_pipeline_execution_id = (
        resolved_state.pipelines.configuration.latest_known_execution_id
        if resolved_state
        else None
    )
    last_push = resolved_state.configuration.last_push if resolved_state else None
    last_pull = resolved_state.configuration.last_pull if resolved_state else None
    sync_baseline = resolved_state.configuration.sync if resolved_state else None
    synchronization = ConfigurationSynchronizationStatus(
        has_state=resolved_state is not None,
        recorded_pipeline_execution_id=recorded_pipeline_execution_id,
        uploaded_at=last_push.recorded_at if last_push else None,
        downloaded_at=last_pull.recorded_at if last_pull else None,
        artifact_etag=sync_baseline.artifact_etag if sync_baseline else None,
        artifact_version_id=sync_baseline.artifact_version_id if sync_baseline else None,
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
