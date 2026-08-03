"""Download customer aws-accelerator-config zip archive from S3 into workspace root and extract."""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import boto3
import typer
from botocore.exceptions import BotoCoreError, ClientError
from rich.console import Console

from lza_workbench.core.workspace import (WORKSPACE_CONFIG_FILE,
                                          WORKSPACE_STATE_FILE,
                                          load_workspace_config,
                                          load_workspace_state,
                                          write_workspace_state)

console = Console()

DEFAULT_ZIP_FILENAME = "aws-accelerator-config.zip"


def resolve_workspace_dir(target_dir: Path | None = None) -> Path:
    """Resolve workspace directory containing lza-workspace.yaml starting from cwd or target_dir."""
    current = (target_dir or Path.cwd()).expanduser().resolve()
    for directory in [current, *current.parents]:
        if (directory / WORKSPACE_CONFIG_FILE).is_file():
            return directory
    raise typer.BadParameter(
        f"Command must be run inside an LZA workspace directory (missing {WORKSPACE_CONFIG_FILE})."
    )


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

    # 1. Read required parameters from config first, prompt for missing parameters if interactive
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

    # Resolve S3 object key and local zip path in root workspace
    s3_bucket, s3_key, zip_name = _resolve_s3_archive_uri(bucket, prefix)
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

    downloaded_files = _download_and_extract_s3_zip(
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
    write_workspace_state(workspace_dir / WORKSPACE_STATE_FILE, state)

    console.print("[bold green]Downloaded and extracted LZA configuration[/bold green]")
    console.print(f"Workspace: {workspace_dir}")
    console.print(f"Source: s3://{s3_bucket}/{s3_key}")
    console.print(f"Zip archive: {zip_path}")
    console.print(f"Extracted to: {config_dir}")
    if downloaded_files:
        console.print("Downloaded files:")
        for fname in downloaded_files:
            console.print(f"  - {fname}")

    return config_dir


def _resolve_s3_archive_uri(bucket: str, prefix: str) -> tuple[str, str, str]:
    """Resolve bucket name, object key, and local zip file name."""
    clean_bucket = bucket.rstrip("/")
    if clean_bucket.endswith(".zip"):
        parts = clean_bucket.split("/", 1)
        s3_bucket = parts[0]
        s3_key = parts[1] if len(parts) > 1 else DEFAULT_ZIP_FILENAME
        zip_name = Path(s3_key).name
        return s3_bucket, s3_key, zip_name

    s3_bucket = clean_bucket
    zip_name = DEFAULT_ZIP_FILENAME
    s3_key = f"{prefix}/{zip_name}".lstrip("/") if prefix else zip_name
    return s3_bucket, s3_key, zip_name


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
) -> list[str]:
    """Download zip archive from S3 into root workspace directory and extract it."""
    try:
        session_kwargs = {}
        if profile:
            session_kwargs["profile_name"] = profile
        if region:
            session_kwargs["region_name"] = region

        session = boto3.Session(**session_kwargs)
        s3 = session.client("s3")

        # Try downloading single zip file directly
        single_zip_success = False
        try:
            s3.download_file(s3_bucket, s3_key, str(zip_path))
            single_zip_success = True
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code not in {"404", "NoSuchKey", "NotFound"}:
                raise

        # If single zip key was not found, search objects under prefix for a .zip file
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
            raise typer.BadParameter(
                f"S3 path not found: s3://{s3_bucket}/{s3_key}"
            ) from exc

        if error_code in {"403", "AccessDenied"}:
            raise typer.BadParameter(
                f"Access denied to s3://{s3_bucket}/{s3_key}. Check your AWS permissions."
            ) from exc

        raise typer.BadParameter(
            f"AWS S3 error [{error_code}]: {error_message}"
        ) from exc

    except BotoCoreError as exc:
        raise typer.BadParameter(
            f"AWS connection/client failure: {exc}"
        ) from exc

    if not extract:
        return [zip_path.name]

    # Extract zip archive into root workspace directory / config_dir
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
) -> list[str]:
    """Extract zip into workspace root, updating config_dir while preserving excluded dirs."""
    with tempfile.TemporaryDirectory() as tmp_str:
        staging_dir = Path(tmp_str)

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(staging_dir)

        # Check if zip contains top-level folder matching config_dir name (aws-accelerator-config)
        top_level_folder = staging_dir / config_dir.name
        if top_level_folder.is_dir():
            source_content_dir = top_level_folder
        else:
            source_content_dir = staging_dir

        config_dir.mkdir(parents=True, exist_ok=True)

        # Remove old files in config_dir while preserving excluded directories (e.g., .git)
        for item in config_dir.iterdir():
            if item.name in exclude_dirs:
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        extracted_files: list[str] = []
        for item in source_content_dir.rglob("*"):
            if item.is_file():
                rel_path = item.relative_to(source_content_dir)
                dest = config_dir / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)
                extracted_files.append(str(rel_path))

        return sorted(extracted_files)
