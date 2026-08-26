"""Workflow for synchronizing local LZA configuration to remote repositories."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from lza_workbench.aws.context import resolve_aws_execution_context
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
from lza_workbench.configuration.schema import get_canonical_config_s3_bucket
from lza_workbench.configuration.state import record_config_git_push, record_config_upload
from lza_workbench.configuration.templates import validate_template
from lza_workbench.errors import LzaError
from lza_workbench.workspace.context import (
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
    bucket_resolver: Callable[[], str] | None = None,
) -> ConfigPushResult:
    """Synchronize local configuration to configured remote repository."""
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED)
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
            bucket_resolver=bucket_resolver,
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
    bucket_resolver: Callable[[], str] | None,
) -> ConfigPushResult:
    repo_cfg = config.configuration.repository
    prefix = repo_cfg.prefix or ""
    key = repo_cfg.key or "aws-accelerator-config.zip"
    if prefix:
        prefix_clean = prefix if prefix.endswith("/") else f"{prefix}/"
        s3_key = f"{prefix_clean}{key}"
    else:
        s3_key = key
    zip_path = workspace_dir / key

    profile = config.aws.profile or ""
    region = config.aws.region

    bucket = repo_cfg.bucket
    if not bucket:
        account_id = config.aws.account_id or (state.management_account_id if state else None)
        if account_id and region:
            bucket = get_canonical_config_s3_bucket(account_id, region)
        elif bucket_resolver is not None:
            bucket = bucket_resolver()
        if not bucket:
            raise LzaError("No S3 bucket configured for LZA configuration repository.")


    if dry_run:
        return ConfigPushResult(
            workspace_dir=workspace_dir,
            config_dir=config_dir,
            repository_type="s3",
            dry_run=True,
            zip_path=zip_path,
            s3_bucket=bucket,
            s3_key=s3_key,
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

    aws_context = resolve_aws_execution_context(
        profile=config.aws.profile,
        region=config.aws.region,
        role_arn=config.aws.role_arn,
        expected_account_id=config.aws.account_id,
        require_identity=True,
        require_expected_account=True,
    )
    s3_client = aws_context.factory.get_client("s3")

    etag, version_id = upload_s3_file(
        client=s3_client,
        file_path=zip_path,
        bucket_name=bucket,
        object_key=s3_key,
    )

    record_config_upload(
        state,
        zip_path=zip_path,
        manifest=zip_manifest,
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
        s3_bucket=bucket,
        s3_key=s3_key,
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
    remote_url = get_git_remote_url(config_dir, remote_name)

    if repo_type == "codecommit":
        if not remote_url:
            repo_name = repo_cfg.repository_name or "aws-accelerator-config"
            region = config.aws.region
            remote_url = f"https://git-codecommit.{region}.amazonaws.com/v1/repos/{repo_name}"
            set_git_remote_url(config_dir, remote_name, remote_url)
        if config.aws.profile:
            configure_codecommit_credential_helper(config_dir, config.aws.profile)
    else:  # codeconnection or git
        if not remote_url:
            if repo_cfg.repository:
                set_git_remote_url(config_dir, remote_name, repo_cfg.repository)
                remote_url = repo_cfg.repository
            else:
                raise LzaError(
                    f"No Git remote '{remote_name}' configured for configuration repository. "
                    "Configure a remote repository before pushing."
                )

    branch = repo_cfg.branch or get_git_branch(config_dir)
    commit = get_git_commit(config_dir)
    files_count = count_git_files(config_dir)

    if dry_run:
        return ConfigPushResult(
            workspace_dir=workspace_dir,
            config_dir=config_dir,
            repository_type=repo_type,
            dry_run=True,
            git_remote=remote_name,
            git_remote_url=remote_url,
            git_branch=branch,
            git_commit=commit,
            files_count=files_count,
        )

    push_git_branch(config_dir, remote=remote_name, branch=branch, dry_run=False)

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
        git_remote_url=remote_url,
        git_branch=branch,
        git_commit=commit,
        files_count=files_count,
    )
