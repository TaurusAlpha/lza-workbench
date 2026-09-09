"""Tests for AWS error classification taxonomy."""

from __future__ import annotations

from botocore.exceptions import ClientError, EndpointConnectionError

from lza_workbench.aws.errors import AwsErrorCategory, classify_aws_error


def _make_client_error(code: str, message: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": message}}, "Operation")


def test_classify_access_denied() -> None:
    for code in ("AccessDenied", "AccessDeniedException", "UnauthorizedOperation", "403"):
        err = _make_client_error(code, "User is not authorized")
        info = classify_aws_error(err)
        assert info.category == AwsErrorCategory.ACCESS_DENIED
        assert info.is_access_denied is True
        assert info.is_unavailable is False
        assert info.is_not_found is False
        assert "User is not authorized" in info.message


def test_classify_not_found() -> None:
    for code in ("StackNotFoundException", "ResourceNotFoundException", "NoSuchBucket", "404"):
        err = _make_client_error(code, "Target not found")
        info = classify_aws_error(err)
        assert info.category == AwsErrorCategory.NOT_FOUND
        assert info.is_not_found is True
        assert info.is_unavailable is False


def test_classify_cfn_validation_not_found() -> None:
    err = _make_client_error("ValidationError", "Stack with id my-stack does not exist")
    info = classify_aws_error(err)
    assert info.category == AwsErrorCategory.NOT_FOUND
    assert info.is_not_found is True


def test_classify_unavailable_client_error() -> None:
    for code in ("ExpiredToken", "ExpiredTokenException", "SSOExpiredTokenException"):
        err = _make_client_error(code, "The security token included in the request is expired")
        info = classify_aws_error(err)
        assert info.category == AwsErrorCategory.UNAVAILABLE
        assert info.is_unavailable is True
        assert "expired" in info.message


def test_classify_unavailable_botocore_error() -> None:
    err = EndpointConnectionError(endpoint_url="https://cloudformation.us-east-1.amazonaws.com")
    info = classify_aws_error(err)
    assert info.category == AwsErrorCategory.UNAVAILABLE
    assert info.is_unavailable is True
    assert "https://" in info.message


def test_classify_generic_api_error() -> None:
    err = _make_client_error("InternalFailure", "An internal error occurred")
    info = classify_aws_error(err)
    assert info.category == AwsErrorCategory.API_ERROR
    assert info.is_unavailable is False
    assert info.is_access_denied is False
    assert info.is_not_found is False
