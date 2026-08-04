"""Download customer aws-accelerator-config zip archive from S3 into workspace root and extract."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console

from lza_workbench.aws.s3 import download_s3_archive, resolve_s3_archive_uri
from lza_workbench.core.workspace import (
    WORKSPACE_CONFIG_FILE,
    WORKSPACE_STATE_FILE,
    ConfigDiffResult,
    count_config_files,
    load_workspace_config,
    load_workspace_state,
    resolve_workspace_dir,
    write_workspace_state,
)
from lza_workbench.utils.archive import extract_zip_to_workspace

console = Console()


def run_download_config(
    *,
    dry_run: bool = False,
    force: bool = False,
    extract: bool = True,
    interactive: bool = False,
    target_dir: Path | None = None,
) -> Path:
    """Download aws-accelerator-config zip archive from S3 into workspace root and extract."""
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
        console.print("[bold]Dry run: lza config download[/bold]")
        console.print(f"Workspace: {workspace_dir}")
        console.print(f"S3 Source: s3://{s3_bucket}/{s3_key}")
        console.print(f"AWS Profile: {profile}")
        console.print(f"AWS Region: {region}")
        console.print(f"Local Zip Path: {zip_path}")
        console.print(f"Extraction Target: {workspace_dir}")
        return config_dir

    if config_dir.exists() and any(config_dir.iterdir()) and not force:
        if interactive:
            confirm = typer.confirm(
                f"Local configuration directory {config_dir} is not empty. Overwrite local files?"
            )
            if not confirm:
                raise typer.Abort()
        else:
            raise typer.BadParameter(
                f"Local configuration directory is not empty: {config_dir}. "
                "Use --force to overwrite."
            )

    exclude_dirs = set(config.configuration.packaging.exclude.directories)

    download_s3_archive(
        s3_bucket=s3_bucket,
        s3_key=s3_key,
        prefix=prefix,
        zip_path=zip_path,
        profile=profile,
        region=region,
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

    write_workspace_state(workspace_dir / WORKSPACE_STATE_FILE, state)

    console.print("[bold green]Downloaded and extracted LZA configuration[/bold green]")
    console.print(f"Workspace: {workspace_dir}")
    console.print(f"Source: s3://{s3_bucket}/{s3_key}")
    console.print(f"Zip archive: {zip_path}")
    console.print(f"Extracted to: {config_dir}")

    _print_diff_summary(diff_result)

    return config_dir


def _print_diff_summary(diff: ConfigDiffResult) -> None:
    """Print clean summary of added, modified, and removed files."""
    if not diff.has_changes:
        console.print("[dim]No file changes detected (configuration up to date).[/dim]")
        return

    console.print(
        f"[bold]Changes: {len(diff.added)} added, "
        f"{len(diff.modified)} modified, {len(diff.removed)} removed[/bold]"
    )
    for fname in diff.added:
        console.print(f"  [green]+ {fname}[/green]")
    for fname in diff.modified:
        console.print(f"  [yellow]~ {fname}[/yellow]")
    for fname in diff.removed:
        console.print(f"  [red]- {fname}[/red]")
