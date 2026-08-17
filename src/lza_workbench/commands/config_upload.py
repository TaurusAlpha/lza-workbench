"""Package and upload customer aws-accelerator-config zip archive to S3."""

from __future__ import annotations

from pathlib import Path

import typer

from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.aws.s3 import upload_s3_archive
from lza_workbench.config.archive import create_zip_archive
from lza_workbench.config.state import record_config_upload
from lza_workbench.config.templates import validate_template
from lza_workbench.config.transfer import resolve_configuration_archive_location
from lza_workbench.errors import LzaError
from lza_workbench.utils.output import (
    print_diff_summary,
    print_dry_run_header,
    print_kv,
    print_success,
)
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context
from lza_workbench.workspace.state import write_workspace_state


def run_upload_config(
    *,
    dry_run: bool = False,
    interactive: bool = False,
    target_dir: Path | None = None,
) -> Path:
    """Package aws-accelerator-config into zip, display change visibility, and upload to S3."""
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED)
    workspace_dir, config, state = ctx.workspace_dir, ctx.config, ctx.state

    config_dir = workspace_dir / config.configuration.local_path

    if not config_dir.exists() or not config_dir.is_dir():
        raise LzaError(f"Configuration directory does not exist: {config_dir}")

    validate_template(config_dir)

    archive_location = resolve_configuration_archive_location(
        workspace_dir=workspace_dir,
        repository=config.configuration.repository,
        prompt_for_bucket=(lambda: typer.prompt("S3 bucket name for configuration"))
        if interactive
        else None,
    )
    profile = config.aws.profile or ""
    region = config.aws.region
    zip_path = archive_location.zip_path

    if dry_run:
        print_dry_run_header("lza config upload")
        print_kv("Workspace", workspace_dir)
        print_kv("Source Directory", config_dir)
        print_kv("Local Zip Path", zip_path)
        print_kv("S3 Target", f"s3://{archive_location.bucket}/{archive_location.key}")
        print_kv("AWS Profile", profile)
        print_kv("AWS Region", region)
        return zip_path

    exclude_dirs = set(config.configuration.packaging.exclude.directories)
    exclude_files = set(config.configuration.packaging.exclude.files)

    diff_result, zip_manifest = create_zip_archive(
        config_dir=config_dir,
        zip_path=zip_path,
        exclude_dirs=exclude_dirs,
        exclude_files=exclude_files,
    )

    aws_context = resolve_aws_execution_context(
        config.aws,
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

    print_success("Packaged and uploaded LZA configuration")
    print_kv("Workspace", workspace_dir)
    print_kv("Zip archive", zip_path)
    print_kv("Destination", f"s3://{archive_location.bucket}/{archive_location.key}")

    print_diff_summary(diff_result.added, diff_result.modified, diff_result.removed)

    return zip_path
