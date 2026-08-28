from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError

from lza_workbench.aws.client_factory import AwsClientFactory
from lza_workbench.errors import LzaError


def _get_sm_client(
    *,
    factory: AwsClientFactory | None = None,
    client: Any | None = None,
) -> Any:
    """Get Secrets Manager client from factory or provided client."""
    if client is not None:
        return client
    if factory is not None:
        return factory.get_client("secretsmanager")
    raise LzaError("Either AwsClientFactory or boto3 client must be provided.")


def inspect_secret_exists(
    secret_name: str,
    client: Any | None = None,
    factory: AwsClientFactory | None = None,
) -> tuple[bool, str | None]:
    """Return whether a resolved secret exists, without feature interpretation."""
    sm_client = _get_sm_client(factory=factory, client=client)
    try:
        sm_client.describe_secret(SecretId=secret_name)
        return True, None
    except ClientError as err:
        code = err.response.get("Error", {}).get("Code")
        if code != "ResourceNotFoundException":
            return False, str(err)
    except Exception as exc:
        return False, str(exc)
    return False, None


def inspect_secret_details(
    secret_name: str,
    client: Any | None = None,
    factory: AwsClientFactory | None = None,
) -> dict[str, Any]:
    """Return existence, accessibility, and string value of a secret."""
    sm_client = _get_sm_client(factory=factory, client=client)
    try:
        sm_client.describe_secret(SecretId=secret_name)
    except ClientError as err:
        code = err.response.get("Error", {}).get("Code")
        if code in ("ResourceNotFoundException", "404"):
            return {"exists": False, "accessible": False, "value": None, "error": None}
        return {"exists": False, "accessible": False, "value": None, "error": str(err)}
    except Exception as exc:
        return {"exists": False, "accessible": False, "value": None, "error": str(exc)}

    try:
        val_resp = sm_client.get_secret_value(SecretId=secret_name)
        secret_string = val_resp.get("SecretString")
        return {"exists": True, "accessible": True, "value": secret_string, "error": None}
    except ClientError as err:
        code = err.response.get("Error", {}).get("Code")
        return {
            "exists": True,
            "accessible": False,
            "value": None,
            "error": f"Access denied: {err}",
        }
    except Exception as exc:
        return {"exists": True, "accessible": False, "value": None, "error": str(exc)}


def create_or_update_secret(
    secret_name: str,
    secret_value: str,
    description: str = "",
    client: Any | None = None,
    factory: AwsClientFactory | None = None,
) -> None:
    """Create or update a secret value in Secrets Manager."""
    sm_client = _get_sm_client(factory=factory, client=client)
    exists, _ = inspect_secret_exists(secret_name, client=sm_client)
    if exists:
        sm_client.put_secret_value(SecretId=secret_name, SecretString=secret_value)
    else:
        sm_client.create_secret(
            Name=secret_name,
            SecretString=secret_value,
            Description=description or "LZA Workbench Secret",
        )


__all__ = [
    "create_or_update_secret",
    "inspect_secret_details",
    "inspect_secret_exists",
]
