"""AWS S3 integration utilities for LZA configuration archives."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from lza_workbench.aws.client_factory import AwsClientFactory
from lza_workbench.core.errors import LzaError

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


def download_s3_archive(
    *,
    s3_bucket: str,
    s3_key: str,
    prefix: str,
    zip_path: Path,
    profile: str | None = None,
    region: str | None = None,
    factory: AwsClientFactory | None = None,
    client: Any | None = None,
) -> None:
    """Fetch zip archive file from S3 using AwsClientFactory."""
    try:
        if client is not None:
            s3 = client
        elif factory is not None:
            s3 = factory.get_client("s3")
        else:
            factory = AwsClientFactory(profile, region)
            s3 = factory.get_client("s3")

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
                raise LzaError(
                    f"S3 archive object not found at s3://{s3_bucket}/{s3_key}"
                )

    except ClientError as exc:
        error = exc.response.get("Error", {})
        error_code = error.get("Code", "Unknown")
        error_message = error.get("Message", str(exc))

        if error_code in {"404", "NoSuchKey", "NoSuchBucket", "NotFound"}:
            raise LzaError(f"S3 path not found: s3://{s3_bucket}/{s3_key}") from exc

        if error_code in {"403", "AccessDenied"}:
            raise LzaError(
                f"Access denied to s3://{s3_bucket}/{s3_key}. Check your AWS permissions."
            ) from exc

        raise LzaError(f"AWS S3 error [{error_code}]: {error_message}") from exc

    except BotoCoreError as exc:
        raise LzaError(f"AWS connection/client failure: {exc}") from exc


def upload_s3_archive(
    *,
    zip_path: Path,
    s3_bucket: str,
    s3_key: str,
    profile: str | None = None,
    region: str | None = None,
    factory: AwsClientFactory | None = None,
    client: Any | None = None,
) -> tuple[str | None, str | None]:
    """Upload local zip archive to S3 bucket and return object (etag, version_id)."""
    try:
        if client is not None:
            s3 = client
        elif factory is not None:
            s3 = factory.get_client("s3")
        else:
            factory = AwsClientFactory(profile, region)
            s3 = factory.get_client("s3")

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
            raise LzaError(f"Target S3 bucket does not exist: s3://{s3_bucket}") from exc

        if error_code in {"403", "AccessDenied"}:
            raise LzaError(
                f"Access denied to s3://{s3_bucket}/{s3_key}. Check AWS permissions."
            ) from exc

        raise LzaError(f"AWS S3 upload error [{error_code}]: {error_message}") from exc

    except BotoCoreError as exc:
        raise LzaError(f"AWS connection/client failure: {exc}") from exc


def ensure_s3_installer_source(
    *,
    factory: AwsClientFactory | None = None,
    client: Any | None = None,
    bucket_name: str,
    region: str | None = None,
) -> None:
    """Ensure S3 bucket for installer source exists, creating it if required."""
    s3_client = (
        client
        if client is not None
        else (factory.get_client("s3") if factory else None)
    )
    if s3_client is None:
        raise ValueError("AWS S3 client is not available")

    clean_bucket = bucket_name.strip()
    try:
        s3_client.head_bucket(Bucket=clean_bucket)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"404", "NoSuchBucket", "NotFound"}:
            kwargs: dict[str, Any] = {"Bucket": clean_bucket}
            if region and region != "us-east-1":
                kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
            s3_client.create_bucket(**kwargs)
        else:
            raise

