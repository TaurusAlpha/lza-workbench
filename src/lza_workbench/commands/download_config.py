"""Download customer aws-accelerator-config from configured LZA repository source into workspace."""

from __future__ import annotations

import shutil
import tarfile
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
    extract: bool = False,
    interactive: bool = False,
    target_dir: Path | None = None,
) -> Path:
    """Download customer aws-accelerator-config from configured repository source."""
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

    if dry_run:
        console.print("[bold]Dry run: lza config download[/bold]")
        console.print(f"Workspace: {workspace_dir}")
        console.print(f"S3 Source: s3://{bucket}/{prefix}")
        console.print(f"AWS Profile: {profile}")
        console.print(f"AWS Region: {region}")
        console.print(f"Target directory: {config_dir}")
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

    downloaded_files = _download_from_s3(
        bucket=bucket,
        prefix=prefix,
        target_dir=config_dir,
        profile=profile,
        region=region,
        extract=extract,
        exclude_dirs=exclude_dirs,
    )

    now = datetime.now(UTC)
    state.updated_at = now
    state.config_downloaded_at = now
    write_workspace_state(workspace_dir / WORKSPACE_STATE_FILE, state)

    console.print("[bold green]Downloaded LZA configuration[/bold green]")
    console.print(f"Workspace: {workspace_dir}")
    console.print(f"Source: s3://{bucket}/{prefix}")
    console.print(f"Downloaded to: {config_dir}")
    if downloaded_files:
        console.print("Downloaded files:")
        for fname in downloaded_files:
            console.print(f"  - {fname}")

    return config_dir


def _download_from_s3(
    *,
    bucket: str,
    prefix: str,
    target_dir: Path,
    profile: str,
    region: str,
    extract: bool,
    exclude_dirs: set[str],
) -> list[str]:
    """Download configuration files from S3 and update target directory atomically."""
    with tempfile.TemporaryDirectory() as tmp_str:
        staging_dir = Path(tmp_str)

        try:
            session_kwargs = {}
            if profile:
                session_kwargs["profile_name"] = profile
            if region:
                session_kwargs["region_name"] = region

            session = boto3.Session(**session_kwargs)
            s3 = session.client("s3")

            paginator = s3.get_paginator("list_objects_v2")
            downloaded_count = 0

            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if key.endswith("/"):
                        continue

                    rel_path = key[len(prefix) :].lstrip("/") if prefix else key
                    if not rel_path:
                        continue

                    dest_file = staging_dir / rel_path
                    dest_file.parent.mkdir(parents=True, exist_ok=True)

                    s3.download_file(bucket, key, str(dest_file))
                    downloaded_count += 1

            if downloaded_count == 0:
                console.print(
                    f"[yellow]Warning: No objects found at s3://{bucket}/{prefix}[/yellow]"
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
                    f"S3 path not found: s3://{bucket}/{prefix}"
                ) from exc

            if error_code in {"403", "AccessDenied"}:
                raise typer.BadParameter(
                    f"Access denied to s3://{bucket}/{prefix}. "
                    "Check your AWS permissions."
                ) from exc

            raise typer.BadParameter(
                f"AWS S3 error [{error_code}]: {error_message}"
            ) from exc

        except BotoCoreError as exc:
            raise typer.BadParameter(
                f"AWS connection/client failure: {exc}"
            ) from exc

        if extract:
            _extract_archives_in_place(staging_dir)

        return _apply_staging_to_target(
            staging_dir,
            target_dir,
            exclude_dirs,
        )


def _extract_archives_in_place(directory: Path) -> None:
    """Extract any archive files found in the directory."""
    for path in list(directory.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path, "r") as zip_ref:
                zip_ref.extractall(directory)
            path.unlink()
        elif path.suffix.lower() in (".tar", ".gz", ".tgz") or path.name.endswith(".tar.gz"):
            with tarfile.open(path, "r:*") as tar_ref:
                tar_ref.extractall(directory)
            path.unlink()


def _apply_staging_to_target(
    staging_dir: Path,
    target_dir: Path,
    exclude_dirs: set[str],
) -> list[str]:
    """Sync files from staging into target_dir while preserving excluded directories."""
    target_dir.mkdir(parents=True, exist_ok=True)

    # Clean existing non-excluded contents in target_dir
    for item in target_dir.iterdir():
        if item.name in exclude_dirs:
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    # Copy files from staging_dir into target_dir
    downloaded_files: list[str] = []
    for item in staging_dir.rglob("*"):
        if item.is_file():
            rel_path = item.relative_to(staging_dir)
            dest = target_dir / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)
            downloaded_files.append(str(rel_path))

    return sorted(downloaded_files)
