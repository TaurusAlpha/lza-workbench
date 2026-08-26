"""AWS S3 service adapter for generic object and bucket operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from lza_workbench.errors import LzaError


def get_s3_https_url(bucket_name: str, object_key: str, region: str = "us-east-1") -> str:
    """Return standard HTTPS URL for an S3 object."""
    clean_bucket = bucket_name.strip()
    clean_key = object_key.strip().lstrip("/")
    clean_region = region.strip()
    if clean_region == "us-east-1":
        return f"https://s3.amazonaws.com/{clean_bucket}/{clean_key}"
    return f"https://s3.{clean_region}.amazonaws.com/{clean_bucket}/{clean_key}"


def get_s3_uri(bucket_name: str, object_key: str) -> str:
    """Return s3:// URI for an S3 object."""
    clean_bucket = bucket_name.strip()
    clean_key = object_key.strip().lstrip("/")
    return f"s3://{clean_bucket}/{clean_key}"


def inspect_s3_bucket(
    *,
    client: Any,
    bucket_name: str,
) -> dict[str, Any]:
    """Inspect S3 bucket existence, accessibility, versioning, and server-side encryption."""
    clean_bucket = bucket_name.strip()
    try:
        client.head_bucket(Bucket=clean_bucket)
    except ClientError as exc:
        error = exc.response.get("Error", {})
        code = error.get("Code", "Unknown")
        if code in {"404", "NoSuchBucket", "NotFound"}:
            return {
                "exists": False,
                "accessible": False,
                "versioning_enabled": False,
                "encryption_enabled": False,
                "kms_encrypted": False,
            }
        if code in {"403", "AccessDenied"}:
            raise LzaError(
                f"Access denied to S3 bucket '{clean_bucket}'. Check your AWS permissions."
            ) from exc
        raise LzaError(f"AWS S3 inspection error on bucket '{clean_bucket}': {exc}") from exc
    except BotoCoreError as exc:
        raise LzaError(f"AWS connection/client failure: {exc}") from exc

    versioning_enabled = False
    try:
        ver_resp = client.get_bucket_versioning(Bucket=clean_bucket)
        versioning_enabled = ver_resp.get("Status") == "Enabled"
    except ClientError:
        pass

    encryption_enabled = False
    kms_encrypted = False
    try:
        enc_resp = client.get_bucket_encryption(Bucket=clean_bucket)
        rules = enc_resp.get("ServerSideEncryptionConfiguration", {}).get("Rules", [])
        if rules:
            encryption_enabled = True
            for rule in rules:
                algo = rule.get("ApplyServerSideEncryptionByDefault", {}).get("SSEAlgorithm")
                if algo == "aws:kms":
                    kms_encrypted = True
                    break
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code not in {
            "ServerSideEncryptionConfigurationNotFoundError",
            "NoSuchServerSideEncryptionRule",
            "404",
            "NotFound",
        }:
            raise LzaError(
                f"Failed to check encryption on S3 bucket '{clean_bucket}': {exc}"
            ) from exc

    return {
        "exists": True,
        "accessible": True,
        "versioning_enabled": versioning_enabled,
        "encryption_enabled": encryption_enabled,
        "kms_encrypted": kms_encrypted,
    }


def create_s3_bucket(
    *,
    client: Any,
    bucket_name: str,
    region: str,
) -> None:
    """Create an S3 bucket in the specified region."""
    clean_bucket = bucket_name.strip()
    kwargs: dict[str, Any] = {"Bucket": clean_bucket}
    if region and region != "us-east-1":
        kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}

    try:
        client.create_bucket(**kwargs)
    except ClientError as exc:
        error = exc.response.get("Error", {})
        code = error.get("Code", "Unknown")
        message = error.get("Message", str(exc))
        if code == "BucketAlreadyOwnedByYou":
            return
        if code == "BucketAlreadyExists":
            raise LzaError(
                f"S3 bucket '{clean_bucket}' already exists in another account or region: {message}"
            ) from exc
        if code in {"403", "AccessDenied"}:
            raise LzaError(
                f"Access denied creating S3 bucket '{clean_bucket}'. Check your AWS permissions."
            ) from exc
        raise LzaError(
            f"AWS connection failure while creating S3 bucket '{clean_bucket}': {exc}"
        ) from exc


def put_s3_bucket_versioning(
    *,
    client: Any,
    bucket_name: str,
    enabled: bool = True,
) -> None:
    """Configure bucket versioning status."""
    clean_bucket = bucket_name.strip()
    status = "Enabled" if enabled else "Suspended"
    try:
        client.put_bucket_versioning(
            Bucket=clean_bucket,
            VersioningConfiguration={"Status": status},
        )
    except (ClientError, BotoCoreError) as exc:
        raise LzaError(
            f"Failed to configure versioning on S3 bucket '{clean_bucket}': {exc}"
        ) from exc


def put_s3_bucket_encryption(
    *,
    client: Any,
    bucket_name: str,
    kms_key_id: str | None = None,
) -> None:
    """Configure default AWS KMS encryption on an S3 bucket."""
    clean_bucket = bucket_name.strip()
    rule_config: dict[str, Any] = {
        "SSEAlgorithm": "aws:kms",
    }
    if kms_key_id:
        rule_config["KMSMasterKeyID"] = kms_key_id

    try:
        client.put_bucket_encryption(
            Bucket=clean_bucket,
            ServerSideEncryptionConfiguration={
                "Rules": [
                    {
                        "ApplyServerSideEncryptionByDefault": rule_config,
                        "BucketKeyEnabled": True,
                    }
                ]
            },
        )
    except (ClientError, BotoCoreError) as exc:
        raise LzaError(
            f"Failed to configure KMS encryption on S3 bucket '{clean_bucket}': {exc}"
        ) from exc


def inspect_s3_object(
    *,
    client: Any,
    bucket_name: str,
    object_key: str,
) -> dict[str, Any]:
    """Inspect S3 object existence and metadata."""
    clean_bucket = bucket_name.strip()
    clean_key = object_key.strip().lstrip("/")
    try:
        return client.head_object(Bucket=clean_bucket, Key=clean_key)
    except ClientError as exc:
        error = exc.response.get("Error", {})
        code = error.get("Code", "Unknown")
        if code in {"404", "NoSuchKey", "NoSuchBucket", "NotFound"}:
            raise LzaError(f"S3 object not found: s3://{clean_bucket}/{clean_key}") from exc
        if code in {"403", "AccessDenied"}:
            raise LzaError(
                f"Access denied to S3 object: s3://{clean_bucket}/{clean_key}"
            ) from exc
        raise LzaError(
            f"AWS S3 inspection error on object 's3://{clean_bucket}/{clean_key}': {exc}"
        ) from exc
    except BotoCoreError as exc:
        raise LzaError(f"AWS connection/client failure: {exc}") from exc


def upload_s3_file(
    *,
    client: Any,
    file_path: Path,
    bucket_name: str,
    object_key: str,
    extra_args: dict[str, Any] | None = None,
) -> tuple[str | None, str | None]:
    """Upload any local file to S3 bucket and return object (etag, version_id)."""
    clean_bucket = bucket_name.strip()
    clean_key = object_key.strip().lstrip("/")
    try:
        kwargs: dict[str, Any] = {}
        if extra_args:
            kwargs["ExtraArgs"] = extra_args

        client.upload_file(str(file_path), clean_bucket, clean_key, **kwargs)

        etag: str | None = None
        version_id: str | None = None
        try:
            head = client.head_object(Bucket=clean_bucket, Key=clean_key)
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
            raise LzaError(f"Target S3 bucket does not exist: s3://{clean_bucket}") from exc

        if error_code in {"403", "AccessDenied"}:
            raise LzaError(
                f"Access denied to s3://{clean_bucket}/{clean_key}. Check AWS permissions."
            ) from exc

        raise LzaError(f"AWS S3 upload error [{error_code}]: {error_message}") from exc

    except BotoCoreError as exc:
        raise LzaError(f"AWS connection/client failure: {exc}") from exc


def download_s3_file(
    *,
    client: Any,
    bucket_name: str,
    object_key: str,
    file_path: Path,
) -> None:
    """Download an S3 object to a local file."""
    clean_bucket = bucket_name.strip()
    clean_key = object_key.strip().lstrip("/")
    try:
        client.download_file(clean_bucket, clean_key, str(file_path))
    except ClientError as exc:
        error = exc.response.get("Error", {})
        error_code = error.get("Code", "Unknown")
        error_message = error.get("Message", str(exc))

        if error_code in {"404", "NoSuchKey", "NoSuchBucket", "NotFound"}:
            raise LzaError(f"S3 path not found: s3://{clean_bucket}/{clean_key}") from exc

        if error_code in {"403", "AccessDenied"}:
            raise LzaError(
                f"Access denied to s3://{clean_bucket}/{clean_key}. Check your AWS permissions."
            ) from exc

        raise LzaError(f"AWS S3 error [{error_code}]: {error_message}") from exc

    except BotoCoreError as exc:
        raise LzaError(f"AWS connection/client failure: {exc}") from exc


def inspect_s3_object_safe(
    *,
    client: Any,
    bucket_name: str,
    object_key: str,
) -> dict[str, Any]:
    """Inspect S3 object existence and metadata returning structured dict without raising on 404."""
    clean_bucket = bucket_name.strip()
    clean_key = object_key.strip().lstrip("/")
    try:
        head = client.head_object(Bucket=clean_bucket, Key=clean_key)
        return {
            "exists": True,
            "etag": head.get("ETag", "").strip('"') or None,
            "version_id": head.get("VersionId"),
            "content_length": head.get("ContentLength"),
            "last_modified": head.get("LastModified"),
            "error": None,
        }
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "Unknown")
        if code in {"404", "NoSuchKey", "NoSuchBucket", "NotFound"}:
            return {
                "exists": False,
                "etag": None,
                "version_id": None,
                "content_length": None,
                "last_modified": None,
                "error": None,
            }
        return {
            "exists": False,
            "etag": None,
            "version_id": None,
            "content_length": None,
            "last_modified": None,
            "error": f"[{code}] {exc}",
        }
    except BotoCoreError as exc:
        return {
            "exists": False,
            "etag": None,
            "version_id": None,
            "content_length": None,
            "last_modified": None,
            "error": f"Connection failure: {exc}",
        }


__all__ = [
    "create_s3_bucket",
    "download_s3_file",
    "get_s3_https_url",
    "get_s3_uri",
    "inspect_s3_bucket",
    "inspect_s3_object",
    "inspect_s3_object_safe",
    "put_s3_bucket_encryption",
    "put_s3_bucket_versioning",
    "upload_s3_file",
]

