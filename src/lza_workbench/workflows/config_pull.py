"""Workflow for synchronizing remote LZA configuration to local workspace."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.aws.s3 import download_s3_file
from lza_workbench.configuration.archive import (
    ConfigDiffResult,
    extract_zip_to_workspace,
)
from lza_workbench.configuration.git import (
    clone_git_repository,
    count_git_files,
    fetch_git_remote,
    get_git_branch,
    get_git_commit,
    get_git_remote_url,
    has_uncommitted_changes,
    init_git_repository,
    is_git_repository,
    pull_git_branch,
    set_git_remote_url,
    stash_git_changes,
)
from lza_workbench.configuration.state import (
    record_config_download,
    record_config_git_pull,
)
from lza_workbench.configuration.templates import validate_template
from lza_workbench.errors import LzaError
from lza_workbench.workspace.context import (
    WorkspaceReadinessLevel,
    load_workspace_context,
)
from lza_workbench.workspace.state import write_workspace_state


@dataclass(frozen=True)
class ConfigPullResult:
    """Structured result of configuration pull / download workflow."""

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
    extracted: bool = True

    # Git specific fields (CodeCommit, CodeConnections, Git)
    git_remote: str | None = None
    git_remote_url: str | None = None
    git_branch: str | None = None
    git_commit: str | None = None
    files_count: int | None = None
    stashed_changes: bool = False


# Alias for backwards compatibility / download command
ConfigDownloadResult = ConfigPullResult


def pull_configuration_workflow(
    *,
    target_dir: Path | None = None,
    dry_run: bool = False,
    force: bool = False,
    extract: bool = True,
    bucket_resolver: Callable[[], str] | None = None,
    overwrite_confirmed: bool = False,
) -> ConfigPullResult:
    """Synchronize remote configuration to local configuration directory."""
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED)
    workspace_dir, config, state = ctx.workspace_dir, ctx.config, ctx.state

    config_dir = workspace_dir / config.configuration.local_path
    repo_cfg = config.configuration.repository
    repo_type = repo_cfg.type

    if repo_type == "s3":
        return _handle_s3_pull(
            workspace_dir=workspace_dir,
            config_dir=config_dir,
            config=config,
            state=state,
            dry_run=dry_run,
            force=force,
            extract=extract,
            bucket_resolver=bucket_resolver,
            overwrite_confirmed=overwrite_confirmed,
        )

    if repo_type in ("codecommit", "codeconnection", "git"):
        return _handle_git_pull(
            workspace_dir=workspace_dir,
            config_dir=config_dir,
            config=config,
            state=state,
            repo_type=repo_type,
            dry_run=dry_run,
            force=force,
            overwrite_confirmed=overwrite_confirmed,
        )

    raise LzaError(f"Unsupported configuration repository type: '{repo_type}'")


def _handle_s3_pull(
    *,
    workspace_dir: Path,
    config_dir: Path,
    config: object,
    state: object,
    dry_run: bool,
    force: bool,
    extract: bool,
    bucket_resolver: Callable[[], str] | None,
    overwrite_confirmed: bool,
) -> ConfigPullResult:
    repo_cfg = config.configuration.repository  # type: ignore[union-attr]
    prefix = repo_cfg.prefix or ""
    key = repo_cfg.key or "aws-accelerator-config.zip"
    if prefix:
        prefix_clean = prefix if prefix.endswith("/") else f"{prefix}/"
        s3_key = f"{prefix_clean}{key}"
    else:
        s3_key = key
    zip_path = workspace_dir / key

    profile = config.aws.profile or ""  # type: ignore[union-attr]
    region = config.aws.region  # type: ignore[union-attr]

    bucket = repo_cfg.bucket
    if not bucket:
        if bucket_resolver is not None:
            bucket = bucket_resolver()
        if not bucket:
            raise LzaError("No S3 bucket configured for LZA configuration repository.")

    if dry_run:
        return ConfigPullResult(
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
            extracted=extract,
        )

    if config_dir.is_dir() and any(config_dir.iterdir()) and not force and not overwrite_confirmed:
        raise LzaError(
            f"Local configuration directory is not empty: {config_dir}. Use --force to overwrite."
        )

    exclude_dirs = set(config.configuration.packaging.exclude.directories)  # type: ignore[union-attr]
    exclude_files = set(config.configuration.packaging.exclude.files)  # type: ignore[union-attr]

    aws_context = resolve_aws_execution_context(
        profile=config.aws.profile,  # type: ignore[union-attr]
        region=config.aws.region,  # type: ignore[union-attr]
        role_arn=config.aws.role_arn,  # type: ignore[union-attr]
        expected_account_id=config.aws.account_id,  # type: ignore[union-attr]
        require_identity=True,
    )
    s3_client = aws_context.factory.get_client("s3")
    download_s3_file(
        client=s3_client,
        bucket_name=bucket,
        object_key=s3_key,
        file_path=zip_path,
    )

    if extract:
        diff_result = extract_zip_to_workspace(
            zip_path=zip_path,
            config_dir=config_dir,
            exclude_dirs=exclude_dirs,
            exclude_files=exclude_files,
        )
        validate_template(config_dir)
    else:
        diff_result = ConfigDiffResult(added=[zip_path.name], modified=[], removed=[])

    record_config_download(
        state,  # type: ignore[arg-type]
        zip_path=zip_path,
        config_dir=config_dir,
        exclude_dirs=exclude_dirs,
        exclude_files=exclude_files,
        diff_result=diff_result,
    )

    write_workspace_state(workspace_dir, state)  # type: ignore[arg-type]

    return ConfigPullResult(
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
        extracted=extract,
    )


def _handle_git_pull(
    *,
    workspace_dir: Path,
    config_dir: Path,
    config: object,
    state: object,
    repo_type: str,
    dry_run: bool,
    force: bool,
    overwrite_confirmed: bool,
) -> ConfigPullResult:
    repo_cfg = config.configuration.repository  # type: ignore[union-attr]
    remote_name = "origin"

    remote_url: str | None = None
    if repo_type == "codecommit":
        repo_name = repo_cfg.repository_name or "aws-accelerator-config"
        region = config.aws.region  # type: ignore[union-attr]
        remote_url = f"https://git-codecommit.{region}.amazonaws.com/v1/repos/{repo_name}"
    else:
        remote_url = repo_cfg.repository

    branch = repo_cfg.branch or "main"

    if dry_run:
        return ConfigPullResult(
            workspace_dir=workspace_dir,
            config_dir=config_dir,
            repository_type=repo_type,
            dry_run=True,
            git_remote=remote_name,
            git_remote_url=remote_url,
            git_branch=branch,
            git_commit=get_git_commit(config_dir) if is_git_repository(config_dir) else None,
            files_count=count_git_files(config_dir) if is_git_repository(config_dir) else None,
        )

    stashed = False
    if not is_git_repository(config_dir):
        if not remote_url:
            raise LzaError(
                f"No remote URL configured for '{repo_type}' configuration repository. "
                "Configure repository settings before pulling."
            )
        if config_dir.exists() and any(config_dir.iterdir()):
            if not force and not overwrite_confirmed:
                raise LzaError(
                    f"Local configuration directory '{config_dir}' is not a Git repository "
                    "and contains files. Use --force to initialize and synchronize."
                )
            init_git_repository(config_dir, remote_name=remote_name, remote_url=remote_url)
            fetch_git_remote(config_dir, remote=remote_name)
            pull_git_branch(config_dir, remote=remote_name, branch=branch)
        else:
            clone_git_repository(config_dir, remote_url=remote_url, branch=branch)
    else:
        existing_url = get_git_remote_url(config_dir, remote_name)
        if not existing_url and remote_url:
            set_git_remote_url(config_dir, remote_name, remote_url)
        elif existing_url:
            remote_url = existing_url

        if has_uncommitted_changes(config_dir):
            if not force and not overwrite_confirmed:
                raise LzaError(
                    "Configuration repository contains uncommitted changes. "
                    "Use --force to automatically stash changes or "
                    "commit/stash them before pulling."
                )
            stashed = stash_git_changes(config_dir)

        fetch_git_remote(config_dir, remote=remote_name)
        current_branch = get_git_branch(config_dir)
        target_branch = branch or current_branch
        pull_git_branch(config_dir, remote=remote_name, branch=target_branch)

    validate_template(config_dir)

    commit = get_git_commit(config_dir)
    files_count = count_git_files(config_dir)

    record_config_git_pull(
        state,  # type: ignore[arg-type]
        files_count=files_count,
        commit_hash=commit,
    )
    write_workspace_state(workspace_dir, state)  # type: ignore[arg-type]

    return ConfigPullResult(
        workspace_dir=workspace_dir,
        config_dir=config_dir,
        repository_type=repo_type,
        dry_run=False,
        git_remote=remote_name,
        git_remote_url=remote_url,
        git_branch=branch,
        git_commit=commit,
        files_count=files_count,
        stashed_changes=stashed,
    )
