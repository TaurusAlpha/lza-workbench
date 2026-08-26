"""Resolved destinations and fixed conventions for LZA configuration repositories."""

from __future__ import annotations

from dataclasses import dataclass

from lza_workbench.configuration.schema import get_canonical_config_s3_bucket
from lza_workbench.errors import LzaError

CONFIG_ARCHIVE_FILENAME = "aws-accelerator-config.zip"
CONFIG_S3_OBJECT_KEY = f"zipped/{CONFIG_ARCHIVE_FILENAME}"


@dataclass(frozen=True)
class S3ConfigurationDestination:
    """The fixed S3 destination for an LZA configuration archive."""

    bucket: str
    object_key: str = CONFIG_S3_OBJECT_KEY


@dataclass(frozen=True)
class GitConfigurationDestination:
    """The configured Git destination for an LZA configuration repository."""

    remote_url: str
    branch: str


def resolve_s3_configuration_destination(
    *,
    configured_bucket: str | None,
    account_id: str | None,
    region: str | None,
) -> S3ConfigurationDestination:
    """Resolve and validate the fixed LZA configuration S3 destination."""
    if not account_id or not region:
        raise LzaError(
            "Cannot resolve the LZA configuration S3 bucket without an AWS account ID and region."
        )

    bucket = get_canonical_config_s3_bucket(account_id, region)
    if configured_bucket and configured_bucket != bucket:
        raise LzaError(
            "Configured S3 bucket does not match the required LZA configuration bucket: "
            f"expected '{bucket}', received '{configured_bucket}'."
        )
    return S3ConfigurationDestination(bucket=bucket)


def resolve_git_configuration_destination(
    *,
    repository_type: str,
    repository_name: str | None,
    repository_url: str | None,
    branch: str | None,
    region: str | None,
) -> GitConfigurationDestination:
    """Resolve the configured Git remote and deployable branch."""
    resolved_branch = branch or "main"
    if repository_type == "codecommit":
        if not region:
            raise LzaError("Cannot resolve the CodeCommit remote without an AWS region.")
        repo_name = repository_name or "lza-config-source"
        return GitConfigurationDestination(
            remote_url=f"https://git-codecommit.{region}.amazonaws.com/v1/repos/{repo_name}",
            branch=resolved_branch,
        )

    if not repository_url:
        raise LzaError(
            f"No remote URL configured for '{repository_type}' configuration repository. "
            "Configure repository settings before synchronizing."
        )
    return GitConfigurationDestination(remote_url=repository_url, branch=resolved_branch)


__all__ = [
    "CONFIG_ARCHIVE_FILENAME",
    "CONFIG_S3_OBJECT_KEY",
    "GitConfigurationDestination",
    "S3ConfigurationDestination",
    "resolve_git_configuration_destination",
    "resolve_s3_configuration_destination",
]
