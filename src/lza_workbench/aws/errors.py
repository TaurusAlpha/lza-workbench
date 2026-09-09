"""AWS error taxonomy and classification for adapters and workflows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from botocore.exceptions import BotoCoreError, ClientError


class AwsErrorCategory(StrEnum):
    """Normalized category of an AWS client or API failure."""

    UNAVAILABLE = "UNAVAILABLE"
    ACCESS_DENIED = "ACCESS_DENIED"
    NOT_FOUND = "NOT_FOUND"
    API_ERROR = "API_ERROR"


@dataclass(frozen=True)
class AwsErrorInfo:
    """Classified AWS error with preserved original message and code."""

    category: AwsErrorCategory
    message: str
    code: str | None = None
    original_exception: Exception | None = None

    @property
    def is_unavailable(self) -> bool:
        """Return True if the error indicates AWS is unreachable or unauthenticated."""
        return self.category == AwsErrorCategory.UNAVAILABLE

    @property
    def is_access_denied(self) -> bool:
        """Return True if authenticated but lacking IAM authorization."""
        return self.category == AwsErrorCategory.ACCESS_DENIED

    @property
    def is_not_found(self) -> bool:
        """Return True if the target resource does not exist."""
        return self.category == AwsErrorCategory.NOT_FOUND


_NOT_FOUND_CODES = frozenset(
    {
        "StackNotFoundException",
        "ResourceNotFoundException",
        "NoSuchBucket",
        "NoSuchKey",
        "NotFound",
        "404",
        "PipelineNotFoundException",
        "RepositoryDoesNotExistException",
        "BranchDoesNotExistException",
        "ConnectionNotFoundException",
        "ParameterNotFound",
        "ServerSideEncryptionConfigurationNotFoundError",
        "NoSuchServerSideEncryptionRule",
    }
)

_ACCESS_DENIED_CODES = frozenset(
    {
        "AccessDenied",
        "AccessDeniedException",
        "UnauthorizedOperation",
        "AuthFailure",
        "ForbiddenException",
        "403",
    }
)

_UNAVAILABLE_CODES = frozenset(
    {
        "ExpiredToken",
        "ExpiredTokenException",
        "RequestExpired",
        "InvalidClientTokenId",
        "UnrecognizedClientException",
        "SSOExpiredTokenException",
        "TokenRetrievalError",
    }
)

_UNAVAILABLE_BOTOCORE_EXCEPTIONS = (
    "EndpointConnectionError",
    "ConnectTimeoutError",
    "ReadTimeoutError",
    "ProxyConnectionError",
    "NoCredentialsError",
    "PartialCredentialsError",
    "CredentialRetrievalError",
    "SSOTokenLoadError",
    "UnauthorizedSSOTokenError",
)


def classify_aws_error(exc: Exception) -> AwsErrorInfo:
    """Classify an exception raised during an AWS client operation."""
    if isinstance(exc, ClientError):
        error_dict = exc.response.get("Error", {})
        code = error_dict.get("Code", "")
        message = error_dict.get("Message", "") or str(exc)

        if code in _ACCESS_DENIED_CODES:
            return AwsErrorInfo(
                category=AwsErrorCategory.ACCESS_DENIED,
                message=message,
                code=code,
                original_exception=exc,
            )

        if code in _NOT_FOUND_CODES:
            return AwsErrorInfo(
                category=AwsErrorCategory.NOT_FOUND,
                message=message,
                code=code,
                original_exception=exc,
            )

        # CloudFormation returns ValidationError with specific message when stack does not exist
        if code == "ValidationError" and "does not exist" in message.lower():
            return AwsErrorInfo(
                category=AwsErrorCategory.NOT_FOUND,
                message=message,
                code=code,
                original_exception=exc,
            )

        if code in _UNAVAILABLE_CODES:
            return AwsErrorInfo(
                category=AwsErrorCategory.UNAVAILABLE,
                message=message,
                code=code,
                original_exception=exc,
            )

        return AwsErrorInfo(
            category=AwsErrorCategory.API_ERROR,
            message=message,
            code=code,
            original_exception=exc,
        )

    exc_type_name = type(exc).__name__
    if isinstance(exc, BotoCoreError) and exc_type_name in _UNAVAILABLE_BOTOCORE_EXCEPTIONS:
        return AwsErrorInfo(
            category=AwsErrorCategory.UNAVAILABLE,
            message=str(exc),
            code=exc_type_name,
            original_exception=exc,
        )

    if isinstance(exc, (ConnectionError, TimeoutError)):
        return AwsErrorInfo(
            category=AwsErrorCategory.UNAVAILABLE,
            message=str(exc),
            code=exc_type_name,
            original_exception=exc,
        )

    # General BotoCoreError or other unexpected exception
    return AwsErrorInfo(
        category=AwsErrorCategory.API_ERROR,
        message=str(exc),
        code=exc_type_name,
        original_exception=exc,
    )
