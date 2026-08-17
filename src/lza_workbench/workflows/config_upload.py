"""Workflow for packaging and uploading LZA configuration archives."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.aws.s3 import upload_s3_archive
from lza_workbench.configuration.archive import (
    ConfigDiffResult,
    create_zip_archive,
)
from lza_workbench.configuration.state import record_config_upload
from lza_workbench.configuration.templates import validate_template
from lza_workbench.configuration.transfer import (
    resolve_configuration_archive_location,
)
from lza_workbench.errors import LzaError
from lza_workbench.workspace.context import (
    WorkspaceReadinessLevel,
    load_workspace_context,
)
from lza_workbench.workspace.state import write_workspace_state


@dataclass(frozen=True)
class ConfigUploadResult:
    """Structured result of configuration upload workflow."""

    workspace_dir: Path
    config_dir: Path
    zip_path: Path
    s3_bucket: str
    s3_key: str
    aws_profile: str
    aws_region: str
    diff_result: ConfigDiffResult
    etag: str | None
    version_id: str | None
    dry_run: bool


def upload_configuration_workflow(
    *,
    target_dir: Path | None = None,
    dry_run: bool = False,
    bucket_resolver: Callable[[], str] | None = None,
) -> ConfigUploadResult:
    """Package and upload configuration archive to S3."""
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED)
    workspace_dir, config, state = ctx.workspace_dir, ctx.config, ctx.state

    config_dir = workspace_dir / config.configuration.local_path

    if not config_dir.exists() or not config_dir.is_dir():
        raise LzaError(f"Configuration directory does not exist: {config_dir}")

    validate_template(config_dir)

    archive_location = resolve_configuration_archive_location(
        workspace_dir=workspace_dir,
        repository=config.configuration.repository,
        prompt_for_bucket=bucket_resolver,
    )
    zip_path = archive_location.zip_path
    profile = config.aws.profile or ""
    region = config.aws.region

    if dry_run:
        return ConfigUploadResult(
            workspace_dir=workspace_dir,
            config_dir=config_dir,
            zip_path=zip_path,
            s3_bucket=archive_location.bucket,
            s3_key=archive_location.key,
            aws_profile=profile,
            aws_region=region,
            diff_result=ConfigDiffResult(added=[], modified=[], removed=[]),
            etag=None,
            version_id=None,
            dry_run=True,
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
    etag, version_id = upload_s3_archive(
        zip_path=zip_path,
        s3_bucket=archive_location.bucket,
        s3_key=archive_location.key,
        factory=aws_context.factory,
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

    return ConfigUploadResult(
        workspace_dir=workspace_dir,
        config_dir=config_dir,
        zip_path=zip_path,
        s3_bucket=archive_location.bucket,
        s3_key=archive_location.key,
        aws_profile=profile,
        aws_region=region,
        diff_result=diff_result,
        etag=etag,
        version_id=version_id,
        dry_run=False,
    )
