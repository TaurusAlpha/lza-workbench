"""AWS CodeConnections integration utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lza_workbench.aws.errors import classify_aws_error


@dataclass(frozen=True)
class CodeConnectionStatusResult:
    """Status and metadata of an AWS CodeConnection."""

    arn: str
    name: str | None = None
    status: str | None = None  # AVAILABLE, PENDING, ERROR, NOT_FOUND, INACCESSIBLE, UNCHECKED
    # Bitbucket, GitHub, GitHubEnterpriseServer, GitLab, GitLabSelfManaged
    provider_type: str | None = None
    owner_account_id: str | None = None
    error: str | None = None


def inspect_codeconnection(
    *,
    client: Any,
    connection_arn: str,
) -> CodeConnectionStatusResult:
    """Inspect CodeConnection status without modifying AWS resources."""
    clean_arn = (connection_arn or "").strip()
    if not clean_arn:
        return CodeConnectionStatusResult(
            arn="",
            status="NOT_SPECIFIED",
            error="Connection ARN is empty",
        )

    try:
        response = client.get_connection(ConnectionArn=clean_arn)
        conn = response.get("Connection", {})
        return CodeConnectionStatusResult(
            arn=clean_arn,
            name=conn.get("ConnectionName"),
            status=conn.get("ConnectionStatus"),
            provider_type=conn.get("ProviderType"),
            owner_account_id=conn.get("OwnerAccountId"),
        )
    except Exception as exc:
        info = classify_aws_error(exc)
        if info.is_not_found:
            return CodeConnectionStatusResult(
                arn=clean_arn,
                status="NOT_FOUND",
                error=info.message,
            )
        if info.is_access_denied:
            return CodeConnectionStatusResult(
                arn=clean_arn,
                status="INACCESSIBLE",
                error=f"AWS Access Denied: {info.message}",
            )
        if info.is_unavailable:
            return CodeConnectionStatusResult(
                arn=clean_arn,
                status="INACCESSIBLE",
                error=f"AWS connection failure: {info.message}",
            )
        return CodeConnectionStatusResult(
            arn=clean_arn,
            status="ERROR",
            error=info.message,
        )


__all__ = [
    "CodeConnectionStatusResult",
    "inspect_codeconnection",
]
