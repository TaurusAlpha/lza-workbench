"""Tests for AWS S3 helper utilities."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from lza_workbench.aws.s3 import (
    DEFAULT_ZIP_FILENAME,
    download_s3_archive,
    resolve_s3_archive_uri,
)
from lza_workbench.errors import LzaError


def test_resolve_s3_archive_uri_with_prefix() -> None:
    bucket, key, zip_name = resolve_s3_archive_uri("my-bucket", "config-prefix")
    assert bucket == "my-bucket"
    assert key == "config-prefix/aws-accelerator-config.zip"
    assert zip_name == DEFAULT_ZIP_FILENAME


def test_resolve_s3_archive_uri_with_zip_bucket() -> None:
    bucket, key, zip_name = resolve_s3_archive_uri("my-bucket/custom.zip", "prefix")
    assert bucket == "my-bucket"
    assert key == "custom.zip"
    assert zip_name == "custom.zip"


def test_resolve_s3_archive_uri_with_prefix_and_key() -> None:
    bucket, key, zip_name = resolve_s3_archive_uri("my-bucket", "zipped/", "custom-config.zip")
    assert bucket == "my-bucket"
    assert key == "zipped/custom-config.zip"
    assert zip_name == "custom-config.zip"


def test_resolve_s3_archive_uri_with_key_only() -> None:
    bucket, key, zip_name = resolve_s3_archive_uri("my-bucket", "", "custom-config.zip")
    assert bucket == "my-bucket"
    assert key == "custom-config.zip"
    assert zip_name == "custom-config.zip"


def test_download_s3_archive_exact_key_success(tmp_path: Path) -> None:
    mock_s3 = MagicMock()
    zip_target = tmp_path / "downloaded.zip"

    download_s3_archive(
        s3_bucket="my-bucket",
        s3_key="zipped/custom.zip",
        zip_path=zip_target,
        client=mock_s3,
    )
    mock_s3.download_file.assert_called_once_with("my-bucket", "zipped/custom.zip", str(zip_target))


def test_download_s3_archive_not_found_raises_lza_error_without_fallback(tmp_path: Path) -> None:
    mock_s3 = MagicMock()
    mock_s3.download_file.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}},
        "GetObject",
    )
    zip_target = tmp_path / "downloaded.zip"

    with pytest.raises(LzaError, match="S3 path not found: s3://my-bucket/zipped/custom.zip"):
        download_s3_archive(
            s3_bucket="my-bucket",
            s3_key="zipped/custom.zip",
            zip_path=zip_target,
            client=mock_s3,
        )

    # Verify no paginator / list_objects fallback was called
    mock_s3.get_paginator.assert_not_called()


def test_download_s3_archive_access_denied(tmp_path: Path) -> None:
    mock_s3 = MagicMock()
    mock_s3.download_file.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
        "GetObject",
    )
    zip_target = tmp_path / "downloaded.zip"

    with pytest.raises(LzaError, match="Access denied to s3://my-bucket/zipped/custom.zip"):
        download_s3_archive(
            s3_bucket="my-bucket",
            s3_key="zipped/custom.zip",
            zip_path=zip_target,
            client=mock_s3,
        )
