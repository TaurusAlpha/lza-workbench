"""Download customer aws-accelerator-config zip archive from S3 into workspace root and extract."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import boto3
import typer
from botocore.exceptions import BotoCoreError, ClientError
from rich.console import Console

from lza_workbench.aws.s3 import resolve_s3_archive_uri
from lza_workbench.core.workspace import (
    WORKSPACE_CONFIG_FILE,
    WORKSPACE_STATE_FILE,
    ConfigDiffResult,
    count_config_files,
    is_path_excluded,
    load_workspace_config,
    load_workspace_state,
    resolve_workspace_dir,
    write_workspace_state,
)

console = Console()


def run_download_config(
    *,
    aws_profile: str = "",
    aws_region: str = "",
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
    profile = aws_profile.strip() or (config.aws.profile or "").strip()
    if not profile and interactive:
        profile = typer.prompt("AWS profile", default=config.customer.slug).strip()
    if not profile:
        raise typer.BadParameter("AWS profile is required but not configured.")

    region = aws_region.strip() or (config.aws.region or "").strip() or "us-east-1"

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

    diff_result = _download_and_extract_s3_zip(
        s3_bucket=s3_bucket,
        s3_key=s3_key,
        prefix=prefix,
        zip_path=zip_path,
        workspace_dir=workspace_dir,
        config_dir=config_dir,
        profile=profile,
        region=region,
        extract=extract,
        exclude_dirs=exclude_dirs,
    )

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


def _download_and_extract_s3_zip(
    *,
    s3_bucket: str,
    s3_key: str,
    prefix: str,
    zip_path: Path,
    workspace_dir: Path,
    config_dir: Path,
    profile: str,
    region: str,
    extract: bool,
    exclude_dirs: set[str],
) -> ConfigDiffResult:
    """Download zip archive from S3 into root workspace directory and extract it."""
    try:
        session_kwargs = {}
        if profile:
            session_kwargs["profile_name"] = profile
        if region:
            session_kwargs["region_name"] = region

        session = boto3.Session(**session_kwargs)
        s3 = session.client("s3")

        single_zip_success = False
        try:
            s3.download_file(s3_bucket, s3_key, str(zip_path))
            single_zip_success = True
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code not in {"404", "NoSuchKey", "NotFound"}:
                raise

        if not single_zip_success:
            paginator = s3.get_paginator("list_objects_v2")
            found_zip_key = None
            for page in paginator.paginate(Bucket=s3_bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if key.endswith(".zip"):
                        found_zip_key = key
                        break
                if found_zip_key:
                    break

            if found_zip_key:
                s3.download_file(s3_bucket, found_zip_key, str(zip_path))
            else:
                raise typer.BadParameter(
                    f"S3 archive object not found at s3://{s3_bucket}/{s3_key}"
                )

    except ImportError as err:
        raise typer.BadParameter(
            "boto3 is required for S3 downloads but is not installed."
        ) from err
    except ClientError as exc:
        error = exc.response.get("Error", {})
        error_code = error.get("Code", "Unknown")
        error_message = error.get("Message", str(exc))

        if error_code in {"404", "NoSuchKey", "NoSuchBucket", "NotFound"}:
            raise typer.BadParameter(f"S3 path not found: s3://{s3_bucket}/{s3_key}") from exc

        if error_code in {"403", "AccessDenied"}:
            raise typer.BadParameter(
                f"Access denied to s3://{s3_bucket}/{s3_key}. Check your AWS permissions."
            ) from exc

        raise typer.BadParameter(f"AWS S3 error [{error_code}]: {error_message}") from exc

    except BotoCoreError as exc:
        raise typer.BadParameter(f"AWS connection/client failure: {exc}") from exc

    if not extract:
        return ConfigDiffResult(added=[zip_path.name], modified=[], removed=[])

    return _extract_zip_to_workspace(
        zip_path=zip_path,
        workspace_dir=workspace_dir,
        config_dir=config_dir,
        exclude_dirs=exclude_dirs,
    )


def _extract_zip_to_workspace(
    *,
    zip_path: Path,
    workspace_dir: Path,
    config_dir: Path,
    exclude_dirs: set[str],
) -> ConfigDiffResult:
    """Extract zip into workspace root, computing added/modified/removed file diffs."""
    with tempfile.TemporaryDirectory() as tmp_str:
        staging_dir = Path(tmp_str)

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(staging_dir)

        top_level_folder = staging_dir / config_dir.name
        if top_level_folder.is_dir():
            source_content_dir = top_level_folder
        else:
            source_content_dir = staging_dir

        before_files = _scan_directory_files(config_dir, exclude_dirs)
        incoming_files = _scan_directory_files(source_content_dir, exclude_dirs)

        before_keys = set(before_files.keys())
        incoming_keys = set(incoming_files.keys())

        added = sorted(list(incoming_keys - before_keys))
        removed = sorted(list(before_keys - incoming_keys))
        modified = [
            k for k in sorted(before_keys & incoming_keys)
            if before_files[k] != incoming_files[k]
        ]

        config_dir.mkdir(parents=True, exist_ok=True)

        for item in config_dir.iterdir():
            if item.name in exclude_dirs:
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        for item in source_content_dir.rglob("*"):
            if item.is_file():
                rel_path = item.relative_to(source_content_dir)
                dest = config_dir / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)

        return ConfigDiffResult(added=added, modified=modified, removed=removed)


def _scan_directory_files(directory: Path, exclude_dirs: set[str]) -> dict[str, str]:
    """Scan directory files and return relative path to sha256 checksum map."""
    files_map: dict[str, str] = {}
    if not directory.is_dir():
        return files_map

    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(directory)
        if is_path_excluded(rel, exclude_dirs):
            continue
        files_map[str(rel)] = hashlib.sha256(path.read_bytes()).hexdigest()

    return files_map


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
