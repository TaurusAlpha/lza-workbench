"""S3 installer source provider."""

from __future__ import annotations

from typing import Any

from lza_workbench.infrastructure.aws.s3 import inspect_s3_bucket


class S3InstallerSourceProvider:
    """S3 source provider for LZA installer pipeline."""

    def __init__(
        self,
        *,
        bucket_name: str,
        object_key: str,
        s3_client: Any = None,
    ) -> None:
        self.bucket_name = bucket_name
        self.object_key = object_key
        self.s3_client = s3_client

    def inspect_prerequisites(self) -> dict[str, Any]:
        """Inspect S3 source bucket status."""
        exists = False
        accessible = False
        if self.s3_client:
            obs = inspect_s3_bucket(client=self.s3_client, bucket_name=self.bucket_name)
            exists = obs.exists
            accessible = obs.accessible

        return {
            "bucket_name": self.bucket_name,
            "object_key": self.object_key,
            "exists": exists,
            "accessible": accessible,
        }

    def validate_readiness(self) -> bool:
        """Validate if the bucket exists and is accessible."""
        if not self.s3_client:
            return True
        obs = inspect_s3_bucket(client=self.s3_client, bucket_name=self.bucket_name)
        return obs.exists and obs.accessible


__all__ = ["S3InstallerSourceProvider"]
