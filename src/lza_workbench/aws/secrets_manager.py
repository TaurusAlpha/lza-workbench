"""Thin AWS Secrets Manager service adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from botocore.exceptions import ClientError


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
    except ClientError as err:
        code = err.response.get("Error", {}).get("Code")
        if code != "ResourceNotFoundException":
            return False, str(err)
    except Exception as exc:
        return False, str(exc)
    return False, None


def inspect_secret_details(
    *,
    client: Any,
    secret_name: str,
) -> SecretObservation:
    """Return existence, accessibility, and string value of a secret."""
    try:
        client.describe_secret(SecretId=secret_name)
    except ClientError as err:
        code = err.response.get("Error", {}).get("Code")
        if code in ("ResourceNotFoundException", "404"):
            return SecretObservation(
                name=secret_name, exists=False, accessible=False, value=None, error=None
            )
        return SecretObservation(
            name=secret_name, exists=False, accessible=False, value=None, error=str(err)
        )
    except Exception as exc:
        return SecretObservation(
            name=secret_name, exists=False, accessible=False, value=None, error=str(exc)
        )

    try:
        val_resp = client.get_secret_value(SecretId=secret_name)
        secret_string = val_resp.get("SecretString")
        return SecretObservation(
            name=secret_name, exists=True, accessible=True, value=secret_string, error=None
        )
    except ClientError as err:
        return SecretObservation(
            name=secret_name,
            exists=True,
            accessible=False,
            value=None,
            error=f"Access denied: {err}",
        )
    except Exception as exc:
        return SecretObservation(
            name=secret_name, exists=True, accessible=False, value=None, error=str(exc)
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
