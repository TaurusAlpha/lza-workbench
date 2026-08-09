"""Package and upload customer aws-accelerator-config zip archive to S3."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import typer

from lza_workbench.aws.client_factory import AwsClientFactory
from lza_workbench.aws.s3 import resolve_s3_archive_uri, upload_s3_archive
from lza_workbench.core.templates import validate_template
from lza_workbench.core.workspace import (
    WORKSPACE_STATE_FILE,
    WorkspaceReadinessLevel,
    load_workspace_context,
    write_workspace_state,
)
from lza_workbench.utils.archive import create_zip_archive
from lza_workbench.utils.output import (
    print_diff_summary,
    print_dry_run_header,
    print_kv,
    print_success,
)


def run_upload_config(
    *,
    dry_run: bool = False,
    interactive: bool = False,
    target_dir: Path | None = None,
) -> Path:
    """Package aws-accelerator-config into zip, display change visibility, and upload to S3."""
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED)
    workspace_dir, config, state = ctx.workspace_dir, ctx.config, ctx.state

    repo_config = config.configuration.repository
    config_dir = workspace_dir / config.configuration.local_path

    if repo_config.type != "s3":
        raise typer.BadParameter(
            f"Unsupported configuration repository type: '{repo_config.type}'. "
            "Only 's3' is supported."
        )

    if not config_dir.exists() or not config_dir.is_dir():
        raise typer.BadParameter(f"Configuration directory does not exist: {config_dir}")

    validate_template(config_dir)

    bucket = (repo_config.bucket or "").strip()
    if not bucket:
        if interactive:
            bucket = typer.prompt("S3 bucket name for configuration").strip()
        if not bucket:
            raise typer.BadParameter(
                "No S3 bucket configured in lza-workspace.yaml under "
                "configuration.repository.bucket."
            )

    prefix = (repo_config.prefix or "").strip()
    profile = config.aws.profile or ""
    region = config.aws.region or "us-east-1"

    s3_bucket, s3_key, zip_name = resolve_s3_archive_uri(bucket, prefix)
    zip_path = workspace_dir / zip_name

    if dry_run:
        print_dry_run_header("lza config upload")
        print_kv("Workspace", workspace_dir)
        print_kv("Source Directory", config_dir)
        print_kv("Local Zip Path", zip_path)
        print_kv("S3 Target", f"s3://{s3_bucket}/{s3_key}")
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

    factory = AwsClientFactory(profile, region)
    etag, version_id = upload_s3_archive(
        zip_path=zip_path,
        s3_bucket=s3_bucket,
        s3_key=s3_key,
        factory=factory,
    )

    now = datetime.now(UTC)
    state.updated_at = now
    state.config_uploaded_at = now
    state.config_artifact_sha256 = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    state.config_artifact_etag = etag
    state.config_artifact_version_id = version_id
    state.config_files_count = len(zip_manifest)
    state.config_last_diff_summary = {
        "added": len(diff_result.added),
        "modified": len(diff_result.modified),
        "removed": len(diff_result.removed),
    }

    write_workspace_state(workspace_dir / WORKSPACE_STATE_FILE, state)

    print_success("Packaged and uploaded LZA configuration")
    print_kv("Workspace", workspace_dir)
    print_kv("Zip archive", zip_path)
    print_kv("Destination", f"s3://{s3_bucket}/{s3_key}")

    print_diff_summary(diff_result.added, diff_result.modified, diff_result.removed)

    return zip_path
