"""Shared configuration archive transfer rules."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from lza_workbench.aws.s3 import resolve_s3_archive_uri
from lza_workbench.configuration.schema import ConfigurationRepositoryConfig
from lza_workbench.errors import LzaError


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
