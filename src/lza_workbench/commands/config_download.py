"""Download customer aws-accelerator-config zip archive from S3 into workspace root and extract."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import typer

from lza_workbench.aws.client_factory import AwsClientFactory
from lza_workbench.aws.s3 import download_s3_archive, resolve_s3_archive_uri
from lza_workbench.core.errors import LzaError
from lza_workbench.utils.archive import (
    ConfigDiffResult,
    count_config_files,
    extract_zip_to_workspace,
)
from lza_workbench.utils.output import (
    print_diff_summary,
    print_dry_run_header,
    print_kv,
    print_success,
)
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context
from lza_workbench.workspace.state import (
    write_workspace_state,
)


def run_download_config(
    *,
    dry_run: bool = False,
    force: bool = False,
    extract: bool = True,
    interactive: bool = False,
    target_dir: Path | None = None,
) -> Path:
    """Download aws-accelerator-config zip archive from S3 into workspace root and extract."""
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED)
    workspace_dir, config, state = ctx.workspace_dir, ctx.config, ctx.state

    repo_config = config.configuration.repository
    config_dir = workspace_dir / config.configuration.local_path

    if repo_config.type != "s3":
        raise LzaError(
            f"Unsupported configuration repository type: '{repo_config.type}'. "
            "Only 's3' is supported."
        )

    bucket = (repo_config.bucket or "").strip()
    if not bucket:
        if interactive:
            bucket = typer.prompt("S3 bucket name for configuration").strip()
        if not bucket:
            raise LzaError(
                "No S3 bucket configured in lza-workspace.yaml under "
                "configuration.repository.bucket."
            )

    prefix = (repo_config.prefix or "").strip()
    profile = config.aws.profile or ""
    region = config.aws.region or "us-east-1"

    s3_bucket, s3_key, zip_name = resolve_s3_archive_uri(bucket, prefix)
    zip_path = workspace_dir / zip_name

    if dry_run:
        print_dry_run_header("lza config download")
        print_kv("Workspace", workspace_dir)
        print_kv("S3 Source", f"s3://{s3_bucket}/{s3_key}")
        print_kv("AWS Profile", profile)
        print_kv("AWS Region", region)
        print_kv("Local Zip Path", zip_path)
        print_kv("Extraction Target", workspace_dir)
        return config_dir

    if config_dir.exists() and any(config_dir.iterdir()) and not force:
        if interactive:
            confirm = typer.confirm(
                f"Local configuration directory {config_dir} is not empty. Overwrite local files?"
            )
            if not confirm:
                raise typer.Abort()
        else:
            raise LzaError(
                f"Local configuration directory is not empty: {config_dir}. "
                "Use --force to overwrite."
            )

    exclude_dirs = set(config.configuration.packaging.exclude.directories)

    factory = AwsClientFactory(profile, region)
    download_s3_archive(
        s3_bucket=s3_bucket,
        s3_key=s3_key,
        prefix=prefix,
        zip_path=zip_path,
        factory=factory,
    )

    if extract:
        diff_result = extract_zip_to_workspace(
            zip_path=zip_path,
            workspace_dir=workspace_dir,
            config_dir=config_dir,
            exclude_dirs=exclude_dirs,
        )
    else:
        diff_result = ConfigDiffResult(added=[zip_path.name], modified=[], removed=[])

    now = datetime.now(UTC)
    state.updated_at = now
    state.config_downloaded_at = now

    if zip_path.exists():
        state.config_artifact_sha256 = hashlib.sha256(zip_path.read_bytes()).hexdigest()

    if config_dir.exists():
        state.config_files_count = count_config_files(config_dir, exclude_dirs)

    state.config_last_diff_summary = {
        "added": len(diff_result.added),
        "modified": len(diff_result.modified),
        "removed": len(diff_result.removed),
    }

    write_workspace_state(workspace_dir / ".lza" / "state.json", state)

    action_str = "Downloaded and extracted " if extract else "Downloaded "
    print_success(f"{action_str}LZA configuration")
    print_kv("Workspace", workspace_dir)
    print_kv("Source", f"s3://{s3_bucket}/{s3_key}")
    print_kv("Zip archive", zip_path)
    print_kv("Extracted to", config_dir)

    print_diff_summary(diff_result.added, diff_result.modified, diff_result.removed)

    return config_dir
