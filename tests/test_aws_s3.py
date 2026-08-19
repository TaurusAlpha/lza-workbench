"""Tests for AWS S3 generic service adapter utilities."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from lza_workbench.aws.s3 import (
    create_s3_bucket,
    download_s3_file,
    get_s3_https_url,
    get_s3_uri,
    inspect_s3_bucket,
    inspect_s3_object,
    put_s3_bucket_encryption,
    put_s3_bucket_versioning,
    upload_s3_file,
)
from lza_workbench.errors import LzaError


def test_download_s3_file_exact_key_success(tmp_path: Path) -> None:
    mock_s3 = MagicMock()
    zip_target = tmp_path / "downloaded.zip"

    download_s3_file(
        client=mock_s3,
        bucket_name="my-bucket",
        object_key="zipped/custom.zip",
        file_path=zip_target,
    )
    mock_s3.download_file.assert_called_once_with("my-bucket", "zipped/custom.zip", str(zip_target))


def test_download_s3_file_not_found_raises_lza_error(tmp_path: Path) -> None:
    mock_s3 = MagicMock()
    mock_s3.download_file.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}},
        "GetObject",
    )
    zip_target = tmp_path / "downloaded.zip"

    with pytest.raises(LzaError, match="S3 path not found: s3://my-bucket/zipped/custom.zip"):
        download_s3_file(
            client=mock_s3,
            bucket_name="my-bucket",
            object_key="zipped/custom.zip",
            file_path=zip_target,
        )


def test_download_s3_file_access_denied(tmp_path: Path) -> None:
    mock_s3 = MagicMock()
    mock_s3.download_file.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
        "GetObject",
    )
    zip_target = tmp_path / "downloaded.zip"

    with pytest.raises(LzaError, match="Access denied to s3://my-bucket/zipped/custom.zip"):
        download_s3_file(
            client=mock_s3,
            bucket_name="my-bucket",
            object_key="zipped/custom.zip",
            file_path=zip_target,
        )


def test_upload_s3_file_success(tmp_path: Path) -> None:
    mock_s3 = MagicMock()
    mock_s3.head_object.return_value = {"ETag": '"test-etag"', "VersionId": "v1.0"}
    sample_file = tmp_path / "sample.txt"
    sample_file.write_text("content", encoding="utf-8")

    etag, ver = upload_s3_file(
        client=mock_s3,
        file_path=sample_file,
        bucket_name="my-bucket",
        object_key="dir/sample.txt",
    )

    assert etag == "test-etag"
    assert ver == "v1.0"
    mock_s3.upload_file.assert_called_once_with(str(sample_file), "my-bucket", "dir/sample.txt")


def test_upload_s3_file_bucket_not_found(tmp_path: Path) -> None:
    mock_s3 = MagicMock()
    mock_s3.upload_file.side_effect = ClientError(
        {"Error": {"Code": "NoSuchBucket", "Message": "The specified bucket does not exist."}},
        "PutObject",
    )
    sample_file = tmp_path / "sample.txt"
    sample_file.write_text("content", encoding="utf-8")

    with pytest.raises(LzaError, match="Target S3 bucket does not exist: s3://my-bucket"):
        upload_s3_file(
            client=mock_s3,
            file_path=sample_file,
            bucket_name="my-bucket",
            object_key="dir/sample.txt",
        )


def test_inspect_s3_object_success() -> None:
    mock_s3 = MagicMock()
    mock_s3.head_object.return_value = {"ContentLength": 1234}

    res = inspect_s3_object(
        client=mock_s3,
        bucket_name="my-bucket",
        object_key="prefix/file.zip",
    )

    assert res["ContentLength"] == 1234
    mock_s3.head_object.assert_called_once_with(Bucket="my-bucket", Key="prefix/file.zip")


def test_inspect_s3_object_not_found() -> None:
    mock_s3 = MagicMock()
    mock_s3.head_object.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}},
        "HeadObject",
    )

    with pytest.raises(LzaError, match="S3 object not found: s3://my-bucket/prefix/file.zip"):
        inspect_s3_object(
            client=mock_s3,
            bucket_name="my-bucket",
            object_key="prefix/file.zip",
        )


def test_inspect_s3_object_access_denied() -> None:
    mock_s3 = MagicMock()
    mock_s3.head_object.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "Forbidden"}},
        "HeadObject",
    )

    with pytest.raises(LzaError, match="Access denied to S3 object: s3://my-bucket/prefix/file.zip"):
        inspect_s3_object(
            client=mock_s3,
            bucket_name="my-bucket",
            object_key="prefix/file.zip",
        )


def test_inspect_s3_bucket_not_found() -> None:
    mock_s3 = MagicMock()
    mock_s3.head_bucket.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}},
        "HeadBucket",
    )
    result = inspect_s3_bucket(client=mock_s3, bucket_name="test-bucket")
    assert result["exists"] is False
    assert result["accessible"] is False
    assert result["versioning_enabled"] is False
    assert result["kms_encrypted"] is False


def test_inspect_s3_bucket_exists_configured() -> None:
    mock_s3 = MagicMock()
    mock_s3.head_bucket.return_value = {}
    mock_s3.get_bucket_versioning.return_value = {"Status": "Enabled"}
    mock_s3.get_bucket_encryption.return_value = {
        "ServerSideEncryptionConfiguration": {
            "Rules": [
                {
                    "ApplyServerSideEncryptionByDefault": {
                        "SSEAlgorithm": "aws:kms",
                    }
                }
            ]
        }
    }
    result = inspect_s3_bucket(client=mock_s3, bucket_name="test-bucket")
    assert result["exists"] is True
    assert result["accessible"] is True
    assert result["versioning_enabled"] is True
    assert result["encryption_enabled"] is True
    assert result["kms_encrypted"] is True


def test_create_s3_bucket_us_east_1() -> None:
    mock_s3 = MagicMock()
    create_s3_bucket(client=mock_s3, bucket_name="test-bucket", region="us-east-1")
    mock_s3.create_bucket.assert_called_once_with(Bucket="test-bucket")


def test_create_s3_bucket_other_region() -> None:
    mock_s3 = MagicMock()
    create_s3_bucket(client=mock_s3, bucket_name="test-bucket", region="eu-west-1")
    mock_s3.create_bucket.assert_called_once_with(
        Bucket="test-bucket",
        CreateBucketConfiguration={"LocationConstraint": "eu-west-1"},
    )


def test_put_s3_bucket_versioning() -> None:
    mock_s3 = MagicMock()
    put_s3_bucket_versioning(client=mock_s3, bucket_name="test-bucket", enabled=True)
    mock_s3.put_bucket_versioning.assert_called_once_with(
        Bucket="test-bucket",
        VersioningConfiguration={"Status": "Enabled"},
    )


def test_put_s3_bucket_encryption() -> None:
    mock_s3 = MagicMock()
    put_s3_bucket_encryption(client=mock_s3, bucket_name="test-bucket")
    mock_s3.put_bucket_encryption.assert_called_once_with(
        Bucket="test-bucket",
        ServerSideEncryptionConfiguration={
            "Rules": [
                {
                    "ApplyServerSideEncryptionByDefault": {
                        "SSEAlgorithm": "aws:kms",
                    },
                    "BucketKeyEnabled": True,
                }
            ]
        },
    )


def test_s3_urls() -> None:
    assert (
        get_s3_https_url("my-bucket", "path/file.zip", "us-east-1")
        == "https://s3.amazonaws.com/my-bucket/path/file.zip"
    )
    assert (
        get_s3_https_url("my-bucket", "path/file.zip", "eu-west-1")
        == "https://s3.eu-west-1.amazonaws.com/my-bucket/path/file.zip"
    )
    assert get_s3_uri("my-bucket", "path/file.zip") == "s3://my-bucket/path/file.zip"
