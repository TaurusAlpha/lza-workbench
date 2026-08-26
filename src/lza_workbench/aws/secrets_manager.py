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
