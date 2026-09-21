"""AWS S3 service adapter for generic object and bucket operations."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from lza_workbench.errors import LzaError
from lza_workbench.infrastructure.aws.errors import classify_aws_error


@dataclass(frozen=True)
class S3BucketObservation:
    exists: bool
    accessible: bool
    versioning_enabled: bool = False
    encryption_enabled: bool = False
    kms_encrypted: bool = False
    tags: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class S3ObjectObservation:
    exists: bool
    etag: str | None = None
    version_id: str | None = None
    content_length: int | None = None
    last_modified: datetime | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    error: str | None = None


def get_s3_https_url(bucket_name: str, object_key: str, region: str = "us-east-1") -> str:
    clean_bucket = bucket_name.strip()
    clean_key = object_key.strip().lstrip("/")
    clean_region = region.strip()
    if clean_region == "us-east-1":
        return f"https://s3.amazonaws.com/{clean_bucket}/{clean_key}"
    return f"https://s3.{clean_region}.amazonaws.com/{clean_bucket}/{clean_key}"


def get_s3_uri(bucket_name: str, object_key: str) -> str:
    clean_bucket = bucket_name.strip()
    clean_key = object_key.strip().lstrip("/")
    return f"s3://{clean_bucket}/{clean_key}"


def inspect_s3_bucket(
    *,
    client: Any,
    bucket_name: str,
) -> S3BucketObservation:
    """Inspect S3 bucket existence, accessibility, versioning, and server-side encryption."""
    clean_bucket = bucket_name.strip()
    try:
        client.head_bucket(Bucket=clean_bucket)
    except Exception as exc:
        info = classify_aws_error(exc)
        if info.is_not_found:
            return S3BucketObservation(exists=False, accessible=False)
        if info.is_access_denied:
            raise LzaError(
                f"Access denied to S3 bucket '{clean_bucket}'. Check your AWS permissions."
            ) from exc
        if info.is_unavailable:
            raise LzaError(f"AWS connection/client failure: {info.message}") from exc
        raise LzaError(
            f"AWS S3 inspection error on bucket '{clean_bucket}': {info.message}"
        ) from exc

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

    tags: dict[str, str] = field(default_factory=dict)
    try:
        tag_resp = client.get_bucket_tagging(Bucket=clean_bucket)
        tags = {item["Key"]: item["Value"] for item in tag_resp.get("TagSet", [])}
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in {"NoSuchTagSet", "404", "NotFound"}:
            raise LzaError(f"Failed to check tags on S3 bucket '{clean_bucket}': {exc}") from exc

    return S3BucketObservation(
        exists=True,
        accessible=True,
        versioning_enabled=versioning_enabled,
        encryption_enabled=encryption_enabled,
        kms_encrypted=kms_encrypted,
        tags=tags,
    )


def create_s3_bucket(
    *,
    client: Any,
    bucket_name: str,
    region: str,
) -> None:
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


def put_s3_bucket_tags(*, client: Any, bucket_name: str, tags: dict[str, str]) -> None:
    """Set the small ownership metadata set used by feature-owned buckets."""
    try:
        client.put_bucket_tagging(
            Bucket=bucket_name.strip(),
            Tagging={"TagSet": [{"Key": key, "Value": value} for key, value in tags.items()]},
        )
    except (ClientError, BotoCoreError) as exc:
        raise LzaError(f"Failed to tag S3 bucket '{bucket_name}': {exc}") from exc


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
) -> S3ObjectObservation:
    clean_bucket = bucket_name.strip()
    clean_key = object_key.strip().lstrip("/")
    try:
        head = client.head_object(Bucket=clean_bucket, Key=clean_key)
        return S3ObjectObservation(
            exists=True,
            etag=head.get("ETag", "").strip('"') or None,
            version_id=head.get("VersionId"),
            content_length=head.get("ContentLength"),
            last_modified=head.get("LastModified"),
            metadata=head.get("Metadata") or {},
        )
    except ClientError as exc:
        error = exc.response.get("Error", {})
        code = error.get("Code", "Unknown")
        if code in {"404", "NoSuchKey", "NoSuchBucket", "NotFound"}:
            raise LzaError(f"S3 object not found: s3://{clean_bucket}/{clean_key}") from exc
        if code in {"403", "AccessDenied"}:
            raise LzaError(f"Access denied to S3 object: s3://{clean_bucket}/{clean_key}") from exc
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


def inspect_s3_object_safe(
    *,
    client: Any,
    bucket_name: str,
    object_key: str,
) -> S3ObjectObservation:
    """Inspect S3 object existence and metadata without raising on a missing object."""
    clean_bucket = bucket_name.strip()
    clean_key = object_key.strip().lstrip("/")
    try:
        head = client.head_object(Bucket=clean_bucket, Key=clean_key)
        return S3ObjectObservation(
            exists=True,
            etag=head.get("ETag", "").strip('"') or None,
            version_id=head.get("VersionId"),
            content_length=head.get("ContentLength"),
            last_modified=head.get("LastModified"),
            metadata=head.get("Metadata") or {},
        )
    except Exception as exc:
        info = classify_aws_error(exc)
        if info.is_not_found:
            return S3ObjectObservation(exists=False)
        prefix = "Connection failure: " if info.is_unavailable else ""
        return S3ObjectObservation(exists=False, error=f"{prefix}{info.message}")


def list_buckets_by_prefix(
    *,
    client: Any,
    prefix: str = "aws-accelerator",
    account_id: str | None = None,
    region: str | None = None,
) -> list[str]:
    clean_prefix = (prefix or "").strip().lower()
    try:
        response = client.list_buckets()
    except (ClientError, BotoCoreError) as exc:
        raise LzaError(f"Failed to list S3 buckets: {exc}") from exc

    pattern: re.Pattern[str] | None = None
    if account_id and region:
        pattern = re.compile(
            rf"^{re.escape(clean_prefix)}-.*?-{re.escape(account_id)}-{re.escape(region)}$",
            re.IGNORECASE,
        )

    matching_buckets: list[str] = []
    for bucket in response.get("Buckets", []):
        bucket_name = bucket.get("Name", "")
        if pattern is not None:
            if pattern.match(bucket_name):
                matching_buckets.append(bucket_name)
        elif bucket_name.lower().startswith(clean_prefix):
            matching_buckets.append(bucket_name)

    return matching_buckets


def empty_and_delete_s3_bucket(
    *,
    client: Any,
    bucket_name: str,
    dry_run: bool = False,
) -> bool:
    """Empty all objects, versions, delete markers, and delete the S3 bucket."""
    clean_bucket = (bucket_name or "").strip()
    if not clean_bucket:
        return False

    if dry_run:
        return False

    try:
        # Delete object versions and delete markers
        paginator = client.get_paginator("list_object_versions")
        for page in paginator.paginate(Bucket=clean_bucket):
            to_delete: list[dict[str, str]] = []
            for version in page.get("Versions", []):
                to_delete.append(
                    {"Key": version["Key"], "VersionId": version["VersionId"]}
                )
            for marker in page.get("DeleteMarkers", []):
                to_delete.append(
                    {"Key": marker["Key"], "VersionId": marker["VersionId"]}
                )

            if to_delete:
                for i in range(0, len(to_delete), 1000):
                    batch = to_delete[i : i + 1000]
                    client.delete_objects(
                        Bucket=clean_bucket, Delete={"Objects": batch}
                    )

        # Delete remaining objects (unversioned fallback)
        obj_paginator = client.get_paginator("list_objects_v2")
        for page in obj_paginator.paginate(Bucket=clean_bucket):
            to_delete = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
            if to_delete:
                for i in range(0, len(to_delete), 1000):
                    batch = to_delete[i : i + 1000]
                    client.delete_objects(
                        Bucket=clean_bucket, Delete={"Objects": batch}
                    )

        client.delete_bucket(Bucket=clean_bucket)
        return True
    except (ClientError, BotoCoreError) as exc:
        raise LzaError(f"Failed to empty and delete S3 bucket '{clean_bucket}': {exc}") from exc


__all__ = [
    "S3BucketObservation",
    "S3ObjectObservation",
    "create_s3_bucket",
    "download_s3_file",
    "empty_and_delete_s3_bucket",
    "get_s3_https_url",
    "get_s3_uri",
    "inspect_s3_bucket",
    "inspect_s3_object",
    "inspect_s3_object_safe",
    "list_buckets_by_prefix",
    "put_s3_bucket_encryption",
    "put_s3_bucket_versioning",
    "upload_s3_file",
]

