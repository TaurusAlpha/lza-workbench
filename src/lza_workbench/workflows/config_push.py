"""Workflow for synchronizing local LZA configuration to remote repositories."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lza_workbench.aws.context import AwsExecutionContext, resolve_aws_execution_context
from lza_workbench.aws.s3 import upload_s3_file
from lza_workbench.configuration.archive import (
    ConfigDiffResult,
    create_zip_archive,
)
from lza_workbench.configuration.git import (
    configure_codecommit_credential_helper,
    count_git_files,
    get_git_branch,
    get_git_commit,
    get_git_remote_url,
    has_commits,
    has_uncommitted_changes,
    is_git_repository,
    push_git_branch,
    set_git_remote_url,
)
from lza_workbench.configuration.repository import (
    CONFIG_ARCHIVE_FILENAME,
    resolve_git_configuration_destination,
    resolve_s3_configuration_destination,
)
from lza_workbench.configuration.state import record_config_git_push, record_config_upload
from lza_workbench.configuration.templates import validate_template
from lza_workbench.errors import LzaError
from lza_workbench.workspace.context import (
    WorkspaceContext,
    WorkspaceReadinessLevel,
    load_workspace_context,
)
from lza_workbench.workspace.schema import WorkspaceConfig, WorkspaceState
from lza_workbench.workspace.state import write_workspace_state


@dataclass(frozen=True)
class ConfigPushResult:
    """Structured result of configuration push / upload workflow."""

    workspace_dir: Path
    config_dir: Path
    repository_type: str
    dry_run: bool

    # S3 specific fields
    zip_path: Path | None = None
    s3_bucket: str | None = None
    s3_key: str | None = None
    aws_profile: str | None = None
    aws_region: str | None = None
    diff_result: ConfigDiffResult | None = None
    etag: str | None = None
    version_id: str | None = None

    # Git specific fields (CodeCommit, CodeConnections, Git)
    git_remote: str | None = None
    git_remote_url: str | None = None
    git_branch: str | None = None
    git_commit: str | None = None
    files_count: int | None = None


# Alias for backwards compatibility
ConfigUploadResult = ConfigPushResult


def push_configuration_workflow(
    *,
    target_dir: Path | None = None,
    dry_run: bool = False,
    workspace_context: WorkspaceContext | None = None,
    aws_context: AwsExecutionContext | None = None,
) -> ConfigPushResult:
    """Synchronize local configuration to configured remote repository."""
    ctx = workspace_context or load_workspace_context(
        target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED
    )
    workspace_dir, config, state = ctx.workspace_dir, ctx.config, ctx.state

    config_dir = workspace_dir / config.configuration.local_path

    if not config_dir.exists() or not config_dir.is_dir():
        raise LzaError(f"Configuration directory does not exist: {config_dir}")

    validate_template(config_dir)

    repo_cfg = config.configuration.repository
    repo_type = repo_cfg.type

    if repo_type == "s3":
        return _handle_s3_push(
            workspace_dir=workspace_dir,
            config_dir=config_dir,
            config=config,
            state=state,
            dry_run=dry_run,
            aws_context=aws_context,
        )

    if repo_type in ("codecommit", "codeconnection", "git"):
        return _handle_git_push(
            workspace_dir=workspace_dir,
            config_dir=config_dir,
            config=config,
            state=state,
            repo_type=repo_type,
            dry_run=dry_run,
        )

    raise LzaError(f"Unsupported configuration repository type: '{repo_type}'")


def _handle_s3_push(
    *,
    workspace_dir: Path,
    config_dir: Path,
    config: WorkspaceConfig,
    state: WorkspaceState,
    dry_run: bool,
    aws_context: AwsExecutionContext | None,
) -> ConfigPushResult:
    repo_cfg = config.configuration.repository
    destination = resolve_s3_configuration_destination(
        configured_bucket=repo_cfg.bucket,
        account_id=config.aws.account_id or state.management_account_id,
        region=config.aws.region,
    )
    zip_path = workspace_dir / CONFIG_ARCHIVE_FILENAME

    profile = config.aws.profile or ""
    region = config.aws.region

    if dry_run:
        return ConfigPushResult(
            workspace_dir=workspace_dir,
            config_dir=config_dir,
            repository_type="s3",
            dry_run=True,
            zip_path=zip_path,
            s3_bucket=destination.bucket,
            s3_key=destination.object_key,
            aws_profile=profile,
            aws_region=region,
            diff_result=ConfigDiffResult(added=[], modified=[], removed=[]),
        )

    exclude_dirs = set(config.configuration.packaging.exclude.directories)
    exclude_files = set(config.configuration.packaging.exclude.files)

    diff_result, zip_manifest = create_zip_archive(
        config_dir=config_dir,
        zip_path=zip_path,
        exclude_dirs=exclude_dirs,
        exclude_files=exclude_files,
    )

    resolved_aws_context = aws_context or resolve_aws_execution_context(
        profile=config.aws.profile,
        region=config.aws.region,
        role_arn=config.aws.role_arn,
        expected_account_id=config.aws.account_id,
        require_identity=True,
        require_expected_account=True,
    )
    s3_client = resolved_aws_context.factory.get_client("s3")

    etag, version_id = upload_s3_file(
        client=s3_client,
        file_path=zip_path,
        bucket_name=destination.bucket,
        object_key=destination.object_key,
    )

    record_config_upload(
        state,
        zip_path=zip_path,
        config_dir=config_dir,
        manifest=zip_manifest,
        exclude_dirs=exclude_dirs,
        exclude_files=exclude_files,
        diff_result=diff_result,
        etag=etag,
        version_id=version_id,
    )

    write_workspace_state(workspace_dir, state)

    return ConfigPushResult(
        workspace_dir=workspace_dir,
        config_dir=config_dir,
        repository_type="s3",
        dry_run=False,
        zip_path=zip_path,
        s3_bucket=destination.bucket,
        s3_key=destination.object_key,
        aws_profile=profile,
        aws_region=region,
        diff_result=diff_result,
        etag=etag,
        version_id=version_id,
    )


def _handle_git_push(
    *,
    workspace_dir: Path,
    config_dir: Path,
    config: WorkspaceConfig,
    state: WorkspaceState,
    repo_type: str,
    dry_run: bool,
) -> ConfigPushResult:
    repo_cfg = config.configuration.repository

    if not is_git_repository(config_dir):
        raise LzaError(
            f"Configuration directory '{config_dir}' is not a Git repository. "
            "Initialize git and commit your configuration before pushing."
        )

    if not has_commits(config_dir):
        raise LzaError(
            f"Configuration Git repository at '{config_dir}' has no commits. "
            "Create an initial commit before pushing."
        )

    if has_uncommitted_changes(config_dir):
        raise LzaError(
            "Configuration repository contains uncommitted changes. "
            "Please commit or stash your changes before pushing."
        )

    remote_name = "origin"
    existing_remote_url = get_git_remote_url(config_dir, remote_name)
    destination = resolve_git_configuration_destination(
        repository_type=repo_type,
        repository_name=repo_cfg.repository_name,
        repository_url=(
            existing_remote_url if repo_type == "codeconnection" else repo_cfg.repository
        ),
        branch=repo_cfg.branch,
        region=config.aws.region,
    )
    if existing_remote_url and existing_remote_url != destination.remote_url:
        raise LzaError(
            f"Git remote '{remote_name}' does not match lza-workspace.yaml: "
            f"expected '{destination.remote_url}', received '{existing_remote_url}'. "
            "Update the local remote before pushing."
        )

    current_branch = get_git_branch(config_dir)
    if current_branch != destination.branch:
        raise LzaError(
            f"Current Git branch '{current_branch}' is not the configured deployable branch "
            f"'{destination.branch}'. Check out '{destination.branch}' before pushing."
        )

    commit = get_git_commit(config_dir)
    files_count = count_git_files(config_dir)

    if dry_run:
        return ConfigPushResult(
            workspace_dir=workspace_dir,
            config_dir=config_dir,
            repository_type=repo_type,
            dry_run=True,
            git_remote=remote_name,
            git_remote_url=destination.remote_url,
            git_branch=destination.branch,
            git_commit=commit,
            files_count=files_count,
        )

    if not existing_remote_url:
        set_git_remote_url(config_dir, remote_name, destination.remote_url)
    if repo_type == "codecommit" and config.aws.profile:
        configure_codecommit_credential_helper(config_dir, config.aws.profile)

    push_git_branch(config_dir, remote=remote_name, branch=destination.branch, dry_run=False)

    record_config_git_push(
        state,
        files_count=files_count,
        commit_hash=commit,
    )
    write_workspace_state(workspace_dir, state)

    return ConfigPushResult(
        workspace_dir=workspace_dir,
        config_dir=config_dir,
        repository_type=repo_type,
        dry_run=False,
        git_remote=remote_name,
        git_remote_url=destination.remote_url,
        git_branch=destination.branch,
        git_commit=commit,
        files_count=files_count,
    )
