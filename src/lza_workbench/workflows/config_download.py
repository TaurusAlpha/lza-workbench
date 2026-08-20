"""Workflow for downloading and extracting LZA configuration archives."""

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
from lza_workbench.configuration.state import record_config_download
from lza_workbench.errors import LzaError
from lza_workbench.workspace.context import (
    WorkspaceReadinessLevel,
    load_workspace_context,
)
from lza_workbench.workspace.state import write_workspace_state

CONFIG_ARCHIVE_KEY = "aws-accelerator-config.zip"


@dataclass(frozen=True)
class ConfigDownloadResult:
    """Structured result of configuration download workflow."""

    workspace_dir: Path
    config_dir: Path
    zip_path: Path
    s3_bucket: str
    s3_key: str
    aws_profile: str
    aws_region: str
    diff_result: ConfigDiffResult
    extracted: bool
    dry_run: bool


def download_configuration_workflow(
    *,
    target_dir: Path | None = None,
    dry_run: bool = False,
    force: bool = False,
    extract: bool = True,
    bucket_resolver: Callable[[], str] | None = None,
    overwrite_confirmed: bool = False,
) -> ConfigDownloadResult:
    """Download and optionally extract configuration archive from S3."""
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED)
    workspace_dir, config, state = ctx.workspace_dir, ctx.config, ctx.state

    config_dir = workspace_dir / config.configuration.local_path
    zip_path = workspace_dir / "aws-accelerator-config.zip"
    profile = config.aws.profile or ""
    region = config.aws.region

    if dry_run:
        return ConfigDownloadResult(
            workspace_dir=workspace_dir,
            config_dir=config_dir,
            zip_path=workspace_dir / "aws-accelerator-config.zip",
            s3_bucket=config.configuration.repository.bucket or "",
            s3_key=CONFIG_ARCHIVE_KEY,
            aws_profile=profile,
            aws_region=region,
            diff_result=ConfigDiffResult(added=[], modified=[], removed=[]),
            extracted=extract,
            dry_run=True,
        )

    if config_dir.exists() and any(config_dir.iterdir()) and not force and not overwrite_confirmed:
        raise LzaError(
            f"Local configuration directory is not empty: {config_dir}. Use --force to overwrite."
        )

    exclude_dirs = set(config.configuration.packaging.exclude.directories)
    exclude_files = set(config.configuration.packaging.exclude.files)

    aws_context = resolve_aws_execution_context(
        profile=config.aws.profile,
        region=config.aws.region,
        role_arn=config.aws.role_arn,
        expected_account_id=config.aws.account_id,
        require_identity=True,
    )
    s3_client = aws_context.factory.get_client("s3")
    download_s3_file(
        client=s3_client,
        bucket_name=config.configuration.repository.bucket or "",
        object_key=CONFIG_ARCHIVE_KEY,
        file_path=zip_path,
    )

    if extract:
        diff_result = extract_zip_to_workspace(
            zip_path=zip_path,
            config_dir=config_dir,
            exclude_dirs=exclude_dirs,
            exclude_files=exclude_files,
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
    )

    write_workspace_state(workspace_dir, state)

    return ConfigDownloadResult(
        workspace_dir=workspace_dir,
        config_dir=config_dir,
        zip_path=zip_path,
        s3_bucket=config.configuration.repository.bucket or "",
        s3_key=CONFIG_ARCHIVE_KEY,
        aws_profile=profile,
        aws_region=region,
        diff_result=diff_result,
        extracted=extract,
        dry_run=False,
    )
