"""Tests for AWS S3 helper utilities."""

from __future__ import annotations

from lza_workbench.aws.s3 import DEFAULT_ZIP_FILENAME, resolve_s3_archive_uri


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
