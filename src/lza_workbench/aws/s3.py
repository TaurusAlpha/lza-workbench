"""AWS S3 integration utilities for LZA configuration archives."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from lza_workbench.aws.client_factory import AwsClientFactory
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


def download_s3_archive(
    *,
    s3_bucket: str,
    s3_key: str,
    zip_path: Path,
    prefix: str | None = None,
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
            raise ValueError("An AWS client or AwsClientFactory is required.")

        s3.download_file(s3_bucket, s3_key, str(zip_path))

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
            raise ValueError("An AWS client or AwsClientFactory is required.")

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


def inspect_s3_installer_source(
    *,
    factory: AwsClientFactory | None = None,
    client: Any | None = None,
    bucket_name: str,
    object_key: str,
) -> None:
    """Verify that the configured installer source object is accessible without mutation."""
    s3_client = client if client is not None else (factory.get_client("s3") if factory else None)
    if s3_client is None:
        raise ValueError("AWS S3 client is not available")

    try:
        s3_client.head_object(Bucket=bucket_name.strip(), Key=object_key.strip())
    except ClientError as exc:
        error = exc.response.get("Error", {})
        code = error.get("Code", "Unknown")
        if code in {"404", "NoSuchKey", "NoSuchBucket", "NotFound"}:
            raise LzaError(
                f"Installer source object not found: s3://{bucket_name}/{object_key}"
            ) from exc
        if code in {"403", "AccessDenied"}:
            raise LzaError(
                f"Access denied to installer source: s3://{bucket_name}/{object_key}"
            ) from exc
        raise LzaError(f"Unable to inspect installer source: {exc}") from exc


def get_workbench_assets_bucket_name(account_id: str, region: str) -> str:
    """Derive standard LZA Workbench assets bucket name."""
    clean_account = account_id.strip()
    clean_region = region.strip()
    return f"s3-lza-workbench-assets-{clean_account}-{clean_region}"


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
        rules = (
            enc_resp.get("ServerSideEncryptionConfiguration", {}).get("Rules", [])
        )
        if rules:
            encryption_enabled = True
            for rule in rules:
                algo = (
                    rule.get("ApplyServerSideEncryptionByDefault", {}).get("SSEAlgorithm")
                )
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


def ensure_s3_workbench_assets_bucket(
    *,
    client: Any,
    bucket_name: str,
    region: str,
) -> list[str]:
    """Ensure the Workbench assets bucket exists, is versioned, and KMS encrypted."""
    actions_taken: list[str] = []
    insp = inspect_s3_bucket(client=client, bucket_name=bucket_name)

    if not insp["exists"]:
        create_s3_bucket(client=client, bucket_name=bucket_name, region=region)
        actions_taken.append(f"Created S3 bucket '{bucket_name}' in region '{region}'")

    if not insp["versioning_enabled"]:
        put_s3_bucket_versioning(client=client, bucket_name=bucket_name, enabled=True)
        actions_taken.append(f"Enabled versioning on S3 bucket '{bucket_name}'")

    if not insp["kms_encrypted"]:
        put_s3_bucket_encryption(client=client, bucket_name=bucket_name)
        actions_taken.append(f"Enabled AWS-managed KMS encryption on S3 bucket '{bucket_name}'")

    if not actions_taken:
        actions_taken.append(f"Reused existing S3 assets bucket '{bucket_name}'")

    return actions_taken
