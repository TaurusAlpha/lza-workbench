"""Thin AWS Secrets Manager service adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lza_workbench.aws.errors import classify_aws_error


@dataclass(frozen=True)
class SecretObservation:
    """Typed observation of an AWS Secrets Manager secret."""

    name: str
    exists: bool
    accessible: bool = False
    value: str | None = None
    error: str | None = None


def inspect_secret_exists(
    *,
    client: Any,
    secret_name: str,
) -> tuple[bool, str | None]:
    """Return whether a resolved secret exists, without feature interpretation."""
    try:
        client.describe_secret(SecretId=secret_name)
        return True, None
    except Exception as exc:
        info = classify_aws_error(exc)
        if info.is_not_found:
            return False, None
        return False, info.message


def inspect_secret_details(
    *,
    client: Any,
    secret_name: str,
) -> SecretObservation:
    """Return existence, accessibility, and string value of a secret."""
    try:
        client.describe_secret(SecretId=secret_name)
    except Exception as exc:
        info = classify_aws_error(exc)
        if info.is_not_found:
            return SecretObservation(
                name=secret_name, exists=False, accessible=False, value=None, error=None
            )
        prefix = "Access denied: " if info.is_access_denied else ""
        return SecretObservation(
            name=secret_name,
            exists=False,
            accessible=False,
            value=None,
            error=f"{prefix}{info.message}",
        )

    try:
        val_resp = client.get_secret_value(SecretId=secret_name)
        secret_string = val_resp.get("SecretString")
        return SecretObservation(
            name=secret_name, exists=True, accessible=True, value=secret_string, error=None
        )
    except Exception as exc:
        info = classify_aws_error(exc)
        prefix = "Access denied: " if info.is_access_denied else ""
        return SecretObservation(
            name=secret_name,
            exists=True,
            accessible=False,
            value=None,
            error=f"{prefix}{info.message}",
        )


def create_or_update_secret(
    *,
    client: Any,
    secret_name: str,
    secret_value: str,
    description: str = "",
) -> None:
    """Create or update a secret value in Secrets Manager."""
    exists, _ = inspect_secret_exists(client=client, secret_name=secret_name)
    if exists:
        client.put_secret_value(SecretId=secret_name, SecretString=secret_value)
    else:
        client.create_secret(
            Name=secret_name,
            SecretString=secret_value,
            Description=description or "LZA Workbench Secret",
        )


__all__ = [
    "SecretObservation",
    "create_or_update_secret",
    "inspect_secret_details",
    "inspect_secret_exists",
]
