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


def inspect_github_secret_token(
    client: Any | None = None,
    factory: AwsClientFactory | None = None,
    secret_name: str = "accelerator/github-token",
) -> str | None:
    """Verify if the specified secret exists in AWS Secrets Manager."""
    sm_client = _get_sm_client(factory=factory, client=client)
    try:
        sm_client.describe_secret(SecretId=secret_name)
        return None
    except ClientError as err:
        code = err.response.get("Error", {}).get("Code")
        if code != "ResourceNotFoundException":
            return f"Secrets Manager check for '{secret_name}' returned: {err}"
    except Exception as exc:
        return f"Secrets Manager check for '{secret_name}' failed: {exc}"

    return (
        "GitHub source selected, but AWS Secrets Manager secret 'accelerator/github-token' "
        "was not found in account/region. "
        "AWS LZA requires a GitHub token stored in Secrets Manager."
    )
