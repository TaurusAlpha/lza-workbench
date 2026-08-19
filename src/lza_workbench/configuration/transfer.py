"""Shared configuration archive transfer rules."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from lza_workbench.configuration.schema import ConfigurationRepositoryConfig
from lza_workbench.errors import LzaError

DEFAULT_ZIP_FILENAME = "aws-accelerator-config.zip"


def resolve_s3_archive_uri(
    bucket: str,
    prefix: str = "",
    key: str | None = None,
) -> tuple[str, str, str]:
    """Resolve bucket name, object key, and local zip file name.

    Returns a tuple of (s3_bucket, s3_key, zip_name).
    """
    clean_bucket = bucket.strip().rstrip("/")
    if clean_bucket.endswith(".zip"):
        parts = clean_bucket.split("/", 1)
        s3_bucket = parts[0]
        s3_key = (
            parts[1]
            if len(parts) > 1
            else (key.strip().lstrip("/") if key and key.strip() else DEFAULT_ZIP_FILENAME)
        )
        zip_name = Path(s3_key).name
        return s3_bucket, s3_key, zip_name

    s3_bucket = clean_bucket
    key_filename = key.strip().lstrip("/") if key and key.strip() else DEFAULT_ZIP_FILENAME
    prefix_clean = prefix.strip().strip("/") if prefix else ""
    if prefix_clean:
        s3_key = f"{prefix_clean}/{key_filename}"
    else:
        s3_key = key_filename
    zip_name = Path(key_filename).name
    return s3_bucket, s3_key, zip_name


@dataclass(frozen=True)
class ConfigurationArchiveLocation:
    """Resolved local and remote location of a configuration archive."""

    bucket: str
    key: str
    zip_path: Path


def resolve_configuration_archive_location(
    *,
    workspace_dir: Path,
    repository: ConfigurationRepositoryConfig,
    prompt_for_bucket: Callable[[], str] | None = None,
) -> ConfigurationArchiveLocation:
    """Validate and resolve the configured S3 configuration archive location."""
    if repository.type != "s3":
        message = f"Unsupported configuration repository type: '{repository.type}'. "
        raise LzaError(f"{message}Only 's3' is supported.")

    bucket = (repository.bucket or "").strip()
    if not bucket and prompt_for_bucket is not None:
        bucket = prompt_for_bucket().strip()
    if not bucket:
        raise LzaError(
            "No S3 bucket configured in lza-workspace.yaml under configuration.repository.bucket."
        )

    s3_bucket, s3_key, zip_name = resolve_s3_archive_uri(
        bucket=bucket,
        prefix=repository.prefix.strip() if repository.prefix else "",
        key=repository.key.strip() if repository.key else None,
    )
    return ConfigurationArchiveLocation(
        bucket=s3_bucket,
        key=s3_key,
        zip_path=workspace_dir / zip_name,
    )


__all__ = [
    "DEFAULT_ZIP_FILENAME",
    "ConfigurationArchiveLocation",
    "resolve_configuration_archive_location",
    "resolve_s3_archive_uri",
]
