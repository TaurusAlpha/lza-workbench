"""Package and upload customer aws-accelerator-config zip archive to S3."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console

from lza_workbench.aws.client_factory import AwsClientFactory
from lza_workbench.aws.s3 import resolve_s3_archive_uri, upload_s3_archive
from lza_workbench.core.templates import validate_template
from lza_workbench.core.workspace import (
    WORKSPACE_CONFIG_FILE,
    WORKSPACE_STATE_FILE,
    ConfigDiffResult,
    load_workspace_config,
    load_workspace_state,
    resolve_workspace_dir,
    write_workspace_state,
)
from lza_workbench.utils.archive import create_zip_archive

console = Console()


def run_upload_config(
    *,
    dry_run: bool = False,
    interactive: bool = False,
    target_dir: Path | None = None,
) -> Path:
    """Package aws-accelerator-config into zip, display change visibility, and upload to S3."""
    workspace_dir = resolve_workspace_dir(target_dir)
    config = load_workspace_config(workspace_dir / WORKSPACE_CONFIG_FILE)
    state = load_workspace_state(workspace_dir / WORKSPACE_STATE_FILE)

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
    profile = (config.aws.profile or "").strip()
    if not profile and interactive:
        profile = typer.prompt("AWS profile", default=config.customer.slug).strip()
    if not profile:
        raise typer.BadParameter("AWS profile is required but not configured.")

    region = (config.aws.region or "").strip() or "us-east-1"

    s3_bucket, s3_key, zip_name = resolve_s3_archive_uri(bucket, prefix)
    zip_path = workspace_dir / zip_name

    if dry_run:
        console.print("[bold]Dry run: lza config upload[/bold]")
        console.print(f"Workspace: {workspace_dir}")
        console.print(f"Source Directory: {config_dir}")
        console.print(f"Local Zip Path: {zip_path}")
        console.print(f"S3 Target: s3://{s3_bucket}/{s3_key}")
        console.print(f"AWS Profile: {profile}")
        console.print(f"AWS Region: {region}")
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

    console.print("[bold green]Packaged and uploaded LZA configuration[/bold green]")
    console.print(f"Workspace: {workspace_dir}")
    console.print(f"Zip archive: {zip_path}")
    console.print(f"Destination: s3://{s3_bucket}/{s3_key}")

    _print_diff_summary(diff_result)

    return zip_path


def _print_diff_summary(diff: ConfigDiffResult) -> None:
    """Print clean summary of added, modified, and removed files."""
    if not diff.has_changes:
        console.print("[dim]No file changes detected in zip archive.[/dim]")
        return

    console.print(
        f"[bold]Archive Changes: {len(diff.added)} added, "
        f"{len(diff.modified)} modified, {len(diff.removed)} removed[/bold]"
    )
    for fname in diff.added:
        console.print(f"  [green]+ {fname}[/green]")
    for fname in diff.modified:
        console.print(f"  [yellow]~ {fname}[/yellow]")
    for fname in diff.removed:
        console.print(f"  [red]- {fname}[/red]")
