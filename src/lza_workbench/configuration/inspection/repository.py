"""Remote configuration repository inspection (S3, CodeCommit, CodeConnections, Git)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from lza_workbench.configuration.inspection.models import (
    CodeCommitConfigurationRepositoryStatus,
    CodeConnectionConfigurationRepositoryStatus,
    ConfigurationRepositoryStatus,
    GitConfigurationRepositoryStatus,
    S3ConfigurationRepositoryStatus,
)
from lza_workbench.configuration.repository import (
    CONFIG_S3_OBJECT_KEY,
    resolve_s3_configuration_destination,
)
from lza_workbench.configuration.sync import (
    RemoteSyncStatus,
    evaluate_s3_remote_sync,
)
from lza_workbench.infrastructure.aws.codecommit import inspect_codecommit_repository
from lza_workbench.infrastructure.aws.codeconnections import inspect_codeconnection
from lza_workbench.infrastructure.aws.s3 import (
    S3ObjectObservation,
    inspect_s3_bucket,
    inspect_s3_object_safe,
)

if TYPE_CHECKING:
    from lza_workbench.workspace.schema import (
        CustomerEnvironmentTarget,
        WorkspaceConfig,
        WorkspaceState,
    )


def inspect_s3_repository_status(
    *,
    repo: Any,
    aws_identity: dict[str, Any] | None,
    region: str,
    factory: Any,
    config_dir: Path | None = None,
    environment_target: CustomerEnvironmentTarget | None = None,
    resolved_config: WorkspaceConfig | None = None,
    resolved_state: WorkspaceState | None = None,
    account_id: str | None = None,
) -> tuple[S3ConfigurationRepositoryStatus, RemoteSyncStatus | None]:
    """Inspect remote S3 configuration bucket and archive object."""
    s3_bucket_name = None
    s3_error = None
    env_target = environment_target or (
        resolved_config.environment_target if resolved_config is not None else None
    )
    resolved_account_id = (
        account_id
        or (env_target.account_id if env_target is not None else None)
        or (resolved_state.observed_account_id if resolved_state is not None else None)
        or (aws_identity.get("account") if aws_identity else None)
    )
    resolved_region = region or (
        env_target.region if env_target is not None else "us-east-1"
    )
    try:
        s3_bucket_name = resolve_s3_configuration_destination(
            configured_bucket=repo.bucket,
            account_id=resolved_account_id,
            region=resolved_region,
        ).bucket
    except Exception as exc:
        s3_error = str(exc)

    s3_bucket_exists = None
    s3_bucket_accessible = None
    s3_bucket_versioning = None
    s3_bucket_encryption = None
    s3_object_exists = None
    s3_object_etag = None
    s3_object_version_id = None
    s3_object_last_modified = None
    s3_object_size = None
    obj_info: S3ObjectObservation | None = None

    if s3_bucket_name and aws_identity:
        try:
            s3_client = factory.get_client("s3")
            b_info = inspect_s3_bucket(client=s3_client, bucket_name=s3_bucket_name)
            s3_bucket_exists = b_info.exists
            s3_bucket_accessible = b_info.accessible
            s3_bucket_versioning = b_info.versioning_enabled
            s3_bucket_encryption = b_info.encryption_enabled

            if s3_bucket_exists:
                obj_info = inspect_s3_object_safe(
                    client=s3_client,
                    bucket_name=s3_bucket_name,
                    object_key=CONFIG_S3_OBJECT_KEY,
                )
                s3_object_exists = obj_info.exists
                s3_object_etag = obj_info.etag
                s3_object_version_id = obj_info.version_id
                s3_object_last_modified = obj_info.last_modified
                s3_object_size = obj_info.content_length
        except Exception as exc:
            s3_error = str(exc)
            s3_bucket_accessible = False

    remote_sync: RemoteSyncStatus | None = None
    if config_dir is not None:
        exclude_dirs = (
            set(resolved_config.configuration.packaging.exclude.directories)
            if resolved_config is not None
            else {".git"}
        )
        exclude_files = (
            set(resolved_config.configuration.packaging.exclude.files)
            if resolved_config is not None
            else {".DS_Store"}
        )
        remote_sync = evaluate_s3_remote_sync(
            config_dir=config_dir,
            exclude_dirs=exclude_dirs,
            exclude_files=exclude_files,
            s3_object_info=obj_info,
            state=resolved_state,
            is_live=bool(aws_identity),
        )

    repository = S3ConfigurationRepositoryStatus(
        bucket=s3_bucket_name,
        object_key=CONFIG_S3_OBJECT_KEY,
        bucket_exists=s3_bucket_exists,
        bucket_accessible=s3_bucket_accessible,
        bucket_versioning=s3_bucket_versioning,
        bucket_encryption=s3_bucket_encryption,
        object_exists=s3_object_exists,
        object_etag=s3_object_etag,
        object_version_id=s3_object_version_id,
        object_last_modified=s3_object_last_modified,
        object_size=s3_object_size,
        error=s3_error,
    )
    return repository, remote_sync


def inspect_codecommit_repository_status(
    *,
    repo: Any,
    aws_identity: dict[str, Any] | None,
    factory: Any,
) -> CodeCommitConfigurationRepositoryStatus:
    repo_name = repo.repository_name or "aws-accelerator-config"
    branch_name = repo.branch or "main"
    codecommit_exists = None
    codecommit_accessible = None
    codecommit_branch_exists = None
    codecommit_error = None

    if aws_identity:
        try:
            cc_client = factory.get_client("codecommit")
            cc_info = inspect_codecommit_repository(
                client=cc_client, repository_name=repo_name, branch_name=branch_name
            )
            codecommit_exists = cc_info.exists
            codecommit_accessible = cc_info.accessible
            codecommit_branch_exists = cc_info.branch_exists
            codecommit_error = cc_info.error
        except Exception as exc:
            codecommit_error = str(exc)
            codecommit_accessible = False

    return CodeCommitConfigurationRepositoryStatus(
        repository_name=repo_name,
        branch_name=branch_name,
        exists=codecommit_exists,
        accessible=codecommit_accessible,
        branch_exists=codecommit_branch_exists,
        error=codecommit_error,
    )


def inspect_codeconnection_repository_status(
    *,
    repo: Any,
    aws_identity: dict[str, Any] | None,
    factory: Any,
) -> CodeConnectionConfigurationRepositoryStatus:
    codeconnection_status = None
    codeconnection_provider = None
    codeconnection_owner_account = None
    codeconnection_error = None

    if repo.codeconnection_arn and aws_identity:
        conn_client = factory.get_client("codeconnections")
        conn_res = inspect_codeconnection(
            client=conn_client,
            connection_arn=repo.codeconnection_arn,
        )
        codeconnection_status = conn_res.status
        codeconnection_provider = conn_res.provider_type
        codeconnection_owner_account = conn_res.owner_account_id
        codeconnection_error = conn_res.error

    return CodeConnectionConfigurationRepositoryStatus(
        connection_arn=repo.codeconnection_arn,
        owner=repo.owner,
        repository_name=repo.repository_name,
        branch_name=repo.branch,
        status=codeconnection_status,
        provider=codeconnection_provider,
        owner_account=codeconnection_owner_account,
        error=codeconnection_error,
    )


def inspect_configuration_repository(
    *,
    repo: Any,
    aws_identity: dict[str, Any] | None,
    region: str,
    factory: Any,
    config_dir: Path | None = None,
    environment_target: CustomerEnvironmentTarget | None = None,
    resolved_config: WorkspaceConfig | None = None,
    resolved_state: WorkspaceState | None = None,
    git_sync_status: Any = None,
    account_id: str | None = None,
) -> tuple[ConfigurationRepositoryStatus, RemoteSyncStatus | None]:
    """Inspect the configured remote repository based on its type."""
    if repo.type == "s3":
        return inspect_s3_repository_status(
            repo=repo,
            config_dir=config_dir,
            environment_target=environment_target,
            resolved_config=resolved_config,
            resolved_state=resolved_state,
            aws_identity=aws_identity,
            region=region,
            factory=factory,
            account_id=account_id,
        )

    remote_sync = (
        RemoteSyncStatus.from_git_sync(git_sync_status) if git_sync_status is not None else None
    )

    if repo.type == "codecommit":
        repository = inspect_codecommit_repository_status(
            repo=repo,
            aws_identity=aws_identity,
            factory=factory,
        )
    elif repo.type == "codeconnection":
        repository = inspect_codeconnection_repository_status(
            repo=repo,
            aws_identity=aws_identity,
            factory=factory,
        )
    else:
        repository = GitConfigurationRepositoryStatus(
            repository_url=repo.repository,
            repository_name=repo.repository_name,
            branch_name=repo.branch,
        )

    return repository, remote_sync


__all__ = [
    "inspect_codecommit_repository_status",
    "inspect_codeconnection_repository_status",
    "inspect_configuration_repository",
    "inspect_s3_repository_status",
]
