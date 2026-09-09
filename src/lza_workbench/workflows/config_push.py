"""Workflow for synchronizing local LZA configuration to remote repositories."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lza_workbench.aws.context import AwsExecutionContext, resolve_aws_execution_context
from lza_workbench.aws.s3 import upload_s3_file
from lza_workbench.configuration.archive import (
    ConfigDiffResult,
    compute_config_directory_digest,
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
from lza_workbench.configuration.state import (
    record_config_git_push,
    record_config_upload,
)
from lza_workbench.configuration.templates import validate_template
from lza_workbench.errors import LzaError
from lza_workbench.workspace.config import write_workspace_config
from lza_workbench.workspace.context import (
    WorkspaceCapability,
    WorkspaceContext,
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

    safety_warning: str | None = None

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


@dataclass(frozen=True)
class ConfigPushRequest:
    """Intent to synchronize local configuration to its configured destination."""

    target_dir: Path | None = None
    dry_run: bool = False
    force: bool = False
    overwrite_confirmed: bool = False
    workspace_context: WorkspaceContext | None = None
    aws_context: AwsExecutionContext | None = None


@dataclass(frozen=True)
class ConfigPushPreparation:
    """Read-only configuration push assessment for an interface to present."""

    result: ConfigPushResult
    confirmation_message: str | None = None
    confirmation_target: str | None = None


class ConfigPushConfirmationRequired(LzaError):
    """Raised when an S3 upload needs explicit overwrite confirmation."""

    def __init__(self, preparation: ConfigPushPreparation) -> None:
        self.preparation = preparation
        super().__init__(preparation.confirmation_message or "Confirmation is required.")


def prepare_config_push(request: ConfigPushRequest) -> ConfigPushPreparation:
    """Assess a push without uploading or writing workspace state."""
    result = push_configuration_workflow(
        target_dir=request.target_dir,
        dry_run=True,
        force=request.force,
        workspace_context=request.workspace_context,
        aws_context=request.aws_context,
    )
    return ConfigPushPreparation(
        result=result,
        confirmation_message=result.safety_warning if not request.force else None,
        confirmation_target=(f"s3://{result.s3_bucket}/{result.s3_key}")
        if result.safety_warning
        else None,
    )


def apply_config_push(request: ConfigPushRequest) -> ConfigPushResult:
    """Apply a previously assessed push after explicit confirmation when needed."""
    preparation = prepare_config_push(request)
    if request.dry_run:
        return preparation.result
    if preparation.confirmation_message and not request.overwrite_confirmed:
        raise ConfigPushConfirmationRequired(preparation)
    return push_configuration_workflow(
        target_dir=request.target_dir,
        dry_run=request.dry_run,
        force=request.force,
        overwrite_confirmed=request.overwrite_confirmed,
        workspace_context=request.workspace_context,
        aws_context=request.aws_context,
    )


def push_configuration_workflow(
    *,
    target_dir: Path | None = None,
    dry_run: bool = False,
    force: bool = False,
    overwrite_confirmed: bool = False,
    workspace_context: WorkspaceContext | None = None,
    aws_context: AwsExecutionContext | None = None,
) -> ConfigPushResult:
    """Synchronize local configuration to configured remote repository."""
    ctx = workspace_context or load_workspace_context(
        target_dir, required_capabilities=(WorkspaceCapability.METADATA_VALID,)
    )
    workspace_dir, config, state = ctx.workspace_dir, ctx.config, ctx.state
    config_dir = ctx.config_dir

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
            force=force,
            overwrite_confirmed=overwrite_confirmed,
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
    force: bool,
    overwrite_confirmed: bool,
) -> ConfigPushResult:
    repo_cfg = config.configuration.repository
    destination = resolve_s3_configuration_destination(
        configured_bucket=repo_cfg.bucket,
        account_id=config.aws.account_id or state.management_account_id,
        region=config.aws.region,
    )
    safety_warning = None
    if state.imported and state.config_sync_digest is None:
        safety_warning = (
            "Remote S3 configuration has not been verified for this imported workspace. "
            "Local configuration may overwrite unknown remote state. "
            "Run `lza config download` first, or use --force to explicitly override this check."
        )
        if not dry_run and not force and not overwrite_confirmed:
            raise LzaError(safety_warning)

    zip_path = workspace_dir / CONFIG_ARCHIVE_FILENAME

    profile = config.aws.profile or ""
    region = config.aws.region

    if dry_run:
        return ConfigPushResult(
            workspace_dir=workspace_dir,
            config_dir=config_dir,
            repository_type="s3",
            dry_run=True,
            safety_warning=safety_warning,
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
        prime_credentials=config.aws.prime_credentials,
    )
    s3_client = resolved_aws_context.factory.get_client("s3")
    if repo_cfg.bucket is None:
        repo_cfg.bucket = destination.bucket
        write_workspace_config(workspace_dir, config)

    sync_digest = compute_config_directory_digest(config_dir, exclude_dirs, exclude_files)
    etag, version_id = upload_s3_file(
        client=s3_client,
        file_path=zip_path,
        bucket_name=destination.bucket,
        object_key=destination.object_key,
        extra_args={"Metadata": {"lza-content-digest": sync_digest}},
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
