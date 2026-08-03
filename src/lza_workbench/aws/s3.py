"""AWS S3 integration utilities for LZA configuration archives."""

from __future__ import annotations

from pathlib import Path

DEFAULT_ZIP_FILENAME = "aws-accelerator-config.zip"


def resolve_s3_archive_uri(bucket: str, prefix: str) -> tuple[str, str, str]:
    """Resolve bucket name, object key, and local zip file name.

    Returns a tuple of (s3_bucket, s3_key, zip_name).
    """
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
