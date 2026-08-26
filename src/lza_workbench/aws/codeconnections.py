"""AWS CodeConnections integration utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from lza_workbench.aws.client_factory import AwsClientFactory


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



def _get_connections_client(
    factory: AwsClientFactory | None = None,
    client: Any | None = None,
) -> Any | None:
    if client is not None:
        return client
    if factory is not None:
        try:
            return factory.get_client("codeconnections")
        except Exception:
            try:
                return factory.get_client("codestar-connections")
            except Exception:
                return None
    return None


def inspect_codeconnection(
    *,
    connection_arn: str,
    client: Any | None = None,
    factory: AwsClientFactory | None = None,
) -> CodeConnectionStatusResult:
    """Inspect CodeConnection status without modifying AWS resources."""
    clean_arn = (connection_arn or "").strip()
    if not clean_arn:
        return CodeConnectionStatusResult(
            arn="",
            status="NOT_SPECIFIED",
            error="Connection ARN is empty",
        )

    conn_client = _get_connections_client(factory=factory, client=client)
    if conn_client is None:
        return CodeConnectionStatusResult(
            arn=clean_arn,
            status="UNCHECKED",
            error="No AWS session or CodeConnections client available",
        )

    try:
        response = conn_client.get_connection(ConnectionArn=clean_arn)
        conn = response.get("Connection", {})
        return CodeConnectionStatusResult(
            arn=clean_arn,
            name=conn.get("ConnectionName"),
            status=conn.get("ConnectionStatus"),
            provider_type=conn.get("ProviderType"),
            owner_account_id=conn.get("OwnerAccountId"),
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        message = exc.response.get("Error", {}).get("Message", str(exc))
        if code in {"ResourceNotFoundException", "ConnectionNotFoundException"}:
            return CodeConnectionStatusResult(
                arn=clean_arn,
                status="NOT_FOUND",
                error=message,
            )
        if code in {"AccessDeniedException", "403"}:
            return CodeConnectionStatusResult(
                arn=clean_arn,
                status="INACCESSIBLE",
                error=f"AWS Access Denied: {message}",
            )
        return CodeConnectionStatusResult(
            arn=clean_arn,
            status="ERROR",
            error=message,
        )
    except BotoCoreError as exc:
        return CodeConnectionStatusResult(
            arn=clean_arn,
            status="INACCESSIBLE",
            error=f"AWS connection failure: {exc}",
        )


__all__ = [
    "CodeConnectionStatusResult",
    "inspect_codeconnection",
]
