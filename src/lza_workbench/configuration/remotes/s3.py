"""S3 configuration remote provider."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lza_workbench.infrastructure.aws.s3 import (
    download_s3_file,
    inspect_s3_bucket,
    upload_s3_file,
)


class S3ConfigurationRemote:
    """Configuration remote backed by an S3 bucket."""

    def __init__(self, *, client: Any, bucket_name: str, key: str = "aws-accelerator-config.zip") -> None:
        self.client = client
        self.bucket_name = bucket_name
        self.key = key

    def inspect(self) -> dict[str, Any]:
        """Inspect the S3 configuration bucket."""
        obs = inspect_s3_bucket(client=self.client, bucket_name=self.bucket_name)
        return {
            "bucket_name": self.bucket_name,
            "exists": obs.exists,
            "accessible": obs.accessible,
            "versioning_enabled": obs.versioning_enabled,
            "encryption_enabled": obs.encryption_enabled,
            "kms_encrypted": obs.kms_encrypted,
        }

    def push(self, local_zip_path: Path, **kwargs: Any) -> tuple[str | None, str | None]:
        """Upload local configuration zip archive to S3 bucket."""
        return upload_s3_file(
            client=self.client,
            file_path=local_zip_path,
            bucket_name=self.bucket_name,
            object_key=self.key,
        )

    def pull(self, destination_zip_path: Path, **kwargs: Any) -> None:
        """Download remote configuration zip archive from S3."""
        download_s3_file(
            client=self.client,
            bucket_name=self.bucket_name,
            object_key=self.key,
            file_path=destination_zip_path,
        )


__all__ = ["S3ConfigurationRemote"]
