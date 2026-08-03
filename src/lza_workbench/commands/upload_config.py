"""Package and upload customer aws-accelerator-config zip archive to S3."""

from __future__ import annotations

import hashlib
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import boto3
import typer
from botocore.exceptions import BotoCoreError, ClientError
from rich.console import Console

from lza_workbench.aws.s3 import resolve_s3_archive_uri
from lza_workbench.core.templates import validate_template
from lza_workbench.core.workspace import (
    WORKSPACE_CONFIG_FILE,
    WORKSPACE_STATE_FILE,
    ConfigDiffResult,
    is_path_excluded,
    load_workspace_config,
    load_workspace_state,
    resolve_workspace_dir,
    write_workspace_state,
)

console = Console()


def run_upload_config(
    *,
    aws_profile: str = "",
    aws_region: str = "",
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
        raise typer.BadParameter(
            f"Configuration directory does not exist: {config_dir}"
        )

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
    profile = aws_profile.strip() or (config.aws.profile or "").strip()
    if not profile and interactive:
        profile = typer.prompt("AWS profile", default=config.customer.slug).strip()
    if not profile:
        raise typer.BadParameter("AWS profile is required but not configured.")

    region = aws_region.strip() or (config.aws.region or "").strip() or "us-east-1"

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

    diff_result, zip_manifest = _create_zip_archive(
        config_dir=config_dir,
        zip_path=zip_path,
        exclude_dirs=exclude_dirs,
        exclude_files=exclude_files,
    )

    etag, version_id = _upload_zip_to_s3(
        zip_path=zip_path,
        s3_bucket=s3_bucket,
        s3_key=s3_key,
        profile=profile,
        region=region,
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


def _create_zip_archive(
    *,
    config_dir: Path,
    zip_path: Path,
    exclude_dirs: set[str],
    exclude_files: set[str],
) -> tuple[ConfigDiffResult, dict[str, tuple[int, int]]]:
    """Create zip archive from config_dir and compute diff against previous zip if present."""
    old_manifest = _read_zip_manifest(zip_path)

    new_manifest: dict[str, tuple[int, int]] = {}
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for path in sorted(config_dir.rglob("*")):
            if not path.is_file():
                continue

            rel_path = path.relative_to(config_dir)
            if is_path_excluded(rel_path, exclude_dirs, exclude_files):
                continue

            arcname = str(rel_path)
            zipf.write(path, arcname)
            info = zipf.getinfo(arcname)
            new_manifest[arcname] = (info.file_size, info.CRC)

    old_keys = set(old_manifest.keys())
    new_keys = set(new_manifest.keys())

    added = sorted(list(new_keys - old_keys))
    removed = sorted(list(old_keys - new_keys))
    modified = [
        k for k in sorted(old_keys & new_keys)
        if old_manifest[k] != new_manifest[k]
    ]

    diff_result = ConfigDiffResult(added=added, modified=modified, removed=removed)
    return diff_result, new_manifest


def _read_zip_manifest(path: Path) -> dict[str, tuple[int, int]]:
    """Read file size and CRC manifest of an existing zip file."""
    manifest: dict[str, tuple[int, int]] = {}
    if not path.is_file():
        return manifest

    try:
        with zipfile.ZipFile(path, "r") as z:
            for info in z.infolist():
                manifest[info.filename] = (info.file_size, info.CRC)
    except zipfile.BadZipFile:
        pass

    return manifest


def _upload_zip_to_s3(
    *,
    zip_path: Path,
    s3_bucket: str,
    s3_key: str,
    profile: str,
    region: str,
) -> tuple[str | None, str | None]:
    """Upload local zip archive to S3 bucket and return object (etag, version_id)."""

    session_kwargs = {}
    if profile:
        session_kwargs["profile_name"] = profile
    if region:
        session_kwargs["region_name"] = region

    try:
        session = boto3.Session(**session_kwargs)
        s3 = session.client("s3")

        s3.upload_file(str(zip_path), s3_bucket, s3_key)

        etag: str | None = None
        version_id: str | None = None
        try:
            head = s3.head_object(Bucket=s3_bucket, Key=s3_key)
            etag = head.get("ETag", "").strip('"') or None
            version_id = head.get("VersionId") or None
        except Exception:
            pass

        return etag, version_id

    except ClientError as exc:
        error = exc.response.get("Error", {})
        error_code = error.get("Code", "Unknown")
        error_message = error.get("Message", str(exc))

        if error_code in {"404", "NoSuchBucket"}:
            raise typer.BadParameter(f"Target S3 bucket does not exist: s3://{s3_bucket}") from exc

        if error_code in {"403", "AccessDenied"}:
            raise typer.BadParameter(
                f"Access denied to s3://{s3_bucket}/{s3_key}. Check AWS permissions."
            ) from exc

        raise typer.BadParameter(f"AWS S3 upload error [{error_code}]: {error_message}") from exc

    except BotoCoreError as exc:
        raise typer.BadParameter(f"AWS connection/client failure: {exc}") from exc


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
