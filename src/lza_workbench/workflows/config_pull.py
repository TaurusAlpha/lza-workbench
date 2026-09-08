"""Workflow for synchronizing remote LZA configuration to local workspace."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.aws.s3 import (
    S3ObjectObservation,
    download_s3_file,
    inspect_s3_object_safe,
)
from lza_workbench.configuration.archive import (
    ConfigDiffResult,
    compute_config_directory_digest,
    extract_zip_to_workspace,
)
from lza_workbench.configuration.git import (
    clone_git_repository,
    configure_codecommit_credential_helper,
    count_git_files,
    fetch_git_remote,
    get_git_branch,
    get_git_commit,
    get_git_remote_url,
    has_uncommitted_changes,
    init_git_repository,
    is_git_repository,
    pull_git_branch,
    restore_git_stash,
    set_git_remote_url,
    stash_git_changes,
)
from lza_workbench.configuration.repository import (
    CONFIG_ARCHIVE_FILENAME,
    resolve_git_configuration_destination,
    resolve_s3_configuration_destination,
)
from lza_workbench.configuration.state import (
    record_config_download,
    record_config_git_pull,
)
from lza_workbench.configuration.templates import validate_template
from lza_workbench.errors import LzaError
from lza_workbench.workspace.config import write_workspace_config
from lza_workbench.workspace.context import (
    WorkspaceCapability,
    load_workspace_context,
)
from lza_workbench.workspace.schema import WorkspaceConfig, WorkspaceState
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
    restored_changes: bool = False


@dataclass(frozen=True)
class ConfigPullRequest:
    """Intent to synchronize remote configuration into a workspace."""

    target_dir: Path | None = None
    dry_run: bool = False
    force: bool = False
    extract: bool = True
    overwrite_confirmed: bool = False


@dataclass(frozen=True)
class ConfigPullPreparation:
    """Read-only configuration pull assessment for an interface to present."""

    result: ConfigPullResult
    confirmation_message: str | None = None
    confirmation_target: Path | None = None
    confirmation_error: str | None = None


class ConfigPullConfirmationRequired(LzaError):
    """Raised when a pull needs explicit local-overwrite confirmation."""

    def __init__(self, preparation: ConfigPullPreparation) -> None:
        self.preparation = preparation
        super().__init__(
            preparation.confirmation_error
            or preparation.confirmation_message
            or "Confirmation is required."
        )


def prepare_config_pull(request: ConfigPullRequest) -> ConfigPullPreparation:
    """Assess a pull without modifying the local configuration or workspace state."""
    result = pull_configuration_workflow(
        target_dir=request.target_dir,
        dry_run=True,
        force=request.force,
        extract=request.extract,
    )
    confirmation_message, confirmation_error = _get_pull_confirmation(
        target_dir=result.workspace_dir,
        config_dir=result.config_dir,
        repository_type=result.repository_type,
        extract=request.extract,
        force=request.force,
    )
    return ConfigPullPreparation(
        result=result,
        confirmation_message=confirmation_message,
        confirmation_target=result.config_dir if confirmation_message else None,
        confirmation_error=confirmation_error,
    )


def apply_config_pull(request: ConfigPullRequest) -> ConfigPullResult:
    """Apply a previously assessed pull after explicit confirmation when needed."""
    preparation = prepare_config_pull(request)
    if request.dry_run:
        return preparation.result
    if preparation.confirmation_message and not request.overwrite_confirmed:
        raise ConfigPullConfirmationRequired(preparation)
    return pull_configuration_workflow(
        target_dir=request.target_dir,
        dry_run=request.dry_run,
        force=request.force,
        extract=request.extract,
        overwrite_confirmed=request.overwrite_confirmed,
    )


def _get_pull_confirmation(
    *,
    target_dir: Path,
    config_dir: Path,
    repository_type: str,
    extract: bool,
    force: bool,
) -> tuple[str | None, str | None]:
    if force:
        return None, None

    context = load_workspace_context(
        target_dir, required_capabilities=(WorkspaceCapability.METADATA_VALID,)
    )
    if repository_type == "s3":
        exclude_dirs = set(context.config.configuration.packaging.exclude.directories)
        exclude_files = set(context.config.configuration.packaging.exclude.files)
        if (
            extract
            and config_dir.is_dir()
            and any(config_dir.iterdir())
            and (
                context.state.config_sync_digest is None
                or compute_config_directory_digest(config_dir, exclude_dirs, exclude_files)
                != context.state.config_sync_digest
            )
        ):
            return (
                f"Local configuration directory '{config_dir}' has uncommitted local changes. "
                "Overwrite?",
                "Local configuration directory is not empty and has changes "
                f"that would be overwritten: {config_dir}. Use --force to overwrite.",
            )
        return None, None

    if not is_git_repository(config_dir):
        if config_dir.exists() and any(config_dir.iterdir()):
            return (
                f"Local configuration directory '{config_dir}' is not a Git repository "
                "and contains files. Initialize Git repository and synchronize remote changes?",
                f"Local configuration directory '{config_dir}' is not a Git repository "
                "and contains files. Use --force to initialize and synchronize.",
            )
        return None, None

    if has_uncommitted_changes(config_dir):
        return (
            "Configuration repository contains uncommitted changes. "
            "Automatically stash local changes and pull?",
            "Configuration repository contains uncommitted changes. "
            "Use --force to automatically stash changes or commit/stash them before pulling.",
        )
    return None, None


def pull_configuration_workflow(
    *,
    target_dir: Path | None = None,
    dry_run: bool = False,
    force: bool = False,
    extract: bool = True,
    overwrite_confirmed: bool = False,
) -> ConfigPullResult:
    """Synchronize remote configuration to local configuration directory."""
    ctx = load_workspace_context(
        target_dir, required_capabilities=(WorkspaceCapability.METADATA_VALID,)
    )
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
    config: WorkspaceConfig,
    state: WorkspaceState,
    dry_run: bool,
    force: bool,
    extract: bool,
    overwrite_confirmed: bool,
) -> ConfigPullResult:
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
        return ConfigPullResult(
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
            extracted=extract,
        )

    exclude_dirs = set(config.configuration.packaging.exclude.directories)
    exclude_files = set(config.configuration.packaging.exclude.files)

    if (
        extract
        and config_dir.is_dir()
        and any(config_dir.iterdir())
        and not force
        and not overwrite_confirmed
        and (
            state.config_sync_digest is None
            or compute_config_directory_digest(config_dir, exclude_dirs, exclude_files)
            != state.config_sync_digest
        )
    ):
        if not overwrite_confirmed:
            raise LzaError(
                "Local configuration directory is not empty and has changes "
                "that would be overwritten: "
                f"{config_dir}. "
                "Use --force to overwrite."
            )

    aws_context = resolve_aws_execution_context(
        profile=config.aws.profile,
        region=config.aws.region,
        role_arn=config.aws.role_arn,
        expected_account_id=config.aws.account_id,
        require_identity=True,
        prime_credentials=config.aws.prime_credentials,
    )
    s3_client = aws_context.factory.get_client("s3")
    if repo_cfg.bucket is None:
        repo_cfg.bucket = destination.bucket
        write_workspace_config(workspace_dir, config)

    s3_info: S3ObjectObservation = inspect_s3_object_safe(
        client=s3_client,
        bucket_name=destination.bucket,
        object_key=destination.object_key,
    )
    etag = s3_info.etag
    version_id = s3_info.version_id

    download_s3_file(
        client=s3_client,
        bucket_name=destination.bucket,
        object_key=destination.object_key,
        file_path=zip_path,
    )

    if extract:
        diff_result = extract_zip_to_workspace(
            zip_path=zip_path,
            config_dir=config_dir,
            exclude_dirs=exclude_dirs,
            exclude_files=exclude_files,
            validate_staged_config=validate_template,
        )
    else:
        diff_result = ConfigDiffResult(added=[zip_path.name], modified=[], removed=[])

    record_config_download(
        state,
        zip_path=zip_path,
        config_dir=config_dir,
        exclude_dirs=exclude_dirs,
        exclude_files=exclude_files,
        diff_result=diff_result,
        extracted=extract,
        etag=etag,
        version_id=version_id,
    )


    write_workspace_state(workspace_dir, state)

    return ConfigPullResult(
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
        extracted=extract,
    )


def _handle_git_pull(
    *,
    workspace_dir: Path,
    config_dir: Path,
    config: WorkspaceConfig,
    state: WorkspaceState,
    repo_type: str,
    dry_run: bool,
    force: bool,
    overwrite_confirmed: bool,
) -> ConfigPullResult:
    repo_cfg = config.configuration.repository
    remote_name = "origin"

    if repo_type == "codeconnection" and not is_git_repository(config_dir):
        raise LzaError(
            "CodeConnection configuration synchronization requires an existing local Git "
            f"repository with a configured '{remote_name}' remote: {config_dir}"
        )

    local_remote_url = get_git_remote_url(config_dir, remote_name)
    destination = resolve_git_configuration_destination(
        repository_type=repo_type,
        repository_name=repo_cfg.repository_name,
        repository_url=local_remote_url if repo_type == "codeconnection" else repo_cfg.repository,
        branch=repo_cfg.branch,
        region=config.aws.region,
    )

    if dry_run:
        return ConfigPullResult(
            workspace_dir=workspace_dir,
            config_dir=config_dir,
            repository_type=repo_type,
            dry_run=True,
            git_remote=remote_name,
            git_remote_url=destination.remote_url,
            git_branch=destination.branch,
            git_commit=get_git_commit(config_dir) if is_git_repository(config_dir) else None,
            files_count=count_git_files(config_dir) if is_git_repository(config_dir) else None,
        )

    stashed = False
    if not is_git_repository(config_dir):
        profile = config.aws.profile if repo_type == "codecommit" else None
        if config_dir.exists() and any(config_dir.iterdir()):
            if not force and not overwrite_confirmed:
                if not overwrite_confirmed:
                    raise LzaError(
                        f"Local configuration directory '{config_dir}' is not a Git repository "
                        "and contains files. Use --force to initialize and synchronize."
                    )
            init_git_repository(
                config_dir,
                remote_name=remote_name,
                remote_url=destination.remote_url,
                aws_profile=profile,
            )
            fetch_git_remote(config_dir, remote=remote_name)
            pull_git_branch(config_dir, remote=remote_name, branch=destination.branch)
        else:
            clone_git_repository(
                config_dir,
                remote_url=destination.remote_url,
                branch=destination.branch,
                aws_profile=profile,
            )
    else:
        existing_url = get_git_remote_url(config_dir, remote_name)
        if not existing_url:
            set_git_remote_url(config_dir, remote_name, destination.remote_url)
        elif existing_url != destination.remote_url:
            raise LzaError(
                f"Git remote '{remote_name}' does not match lza-workspace.yaml: "
                f"expected '{destination.remote_url}', received '{existing_url}'. "
                "Update the local remote before pulling."
            )

        if repo_type == "codecommit" and config.aws.profile:
            configure_codecommit_credential_helper(config_dir, config.aws.profile)

        current_branch = get_git_branch(config_dir)
        if current_branch != destination.branch:
            raise LzaError(
                f"Current Git branch '{current_branch}' is not the configured branch "
                f"'{destination.branch}'. Check out '{destination.branch}' before pulling."
            )

        if has_uncommitted_changes(config_dir):
            if not force and not overwrite_confirmed:
                if not overwrite_confirmed:
                    raise LzaError(
                        "Configuration repository contains uncommitted changes. "
                        "Use --force to automatically stash changes or "
                        "commit/stash them before pulling."
                    )
            stashed = stash_git_changes(config_dir)

        fetch_git_remote(config_dir, remote=remote_name)
        pull_git_branch(config_dir, remote=remote_name, branch=destination.branch)

        if stashed:
            restore_git_stash(config_dir)

    validate_template(config_dir)

    commit = get_git_commit(config_dir)
    files_count = count_git_files(config_dir)

    record_config_git_pull(
        state,
        files_count=files_count,
        commit_hash=commit,
    )
    write_workspace_state(workspace_dir, state)

    return ConfigPullResult(
        workspace_dir=workspace_dir,
        config_dir=config_dir,
        repository_type=repo_type,
        dry_run=False,
        git_remote=remote_name,
        git_remote_url=destination.remote_url,
        git_branch=destination.branch,
        git_commit=commit,
        files_count=files_count,
        stashed_changes=stashed,
        restored_changes=stashed,
    )
