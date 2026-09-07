"""Thin AWS Systems Manager Parameter Store adapter."""

from __future__ import annotations

from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from lza_workbench.aws.client_factory import AwsClientFactory


def get_parameter_value(
    *,
    name: str,
    factory: AwsClientFactory | None = None,
    client: Any | None = None,
) -> str | None:
    """Return a plain SSM parameter value, or ``None`` when it cannot be read."""
    ssm = client or (factory.get_client("ssm") if factory is not None else None)
    if ssm is None or not name.strip():
        return None

    try:
        value = ssm.get_parameter(Name=name).get("Parameter", {}).get("Value")
        return value if isinstance(value, str) and value.strip() else None
    except (ClientError, BotoCoreError):
        return None
