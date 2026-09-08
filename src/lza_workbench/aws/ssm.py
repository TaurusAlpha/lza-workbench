"""Thin AWS Systems Manager Parameter Store adapter."""

from __future__ import annotations

from typing import Any

from botocore.exceptions import BotoCoreError, ClientError


def get_parameter_value(
    *,
    client: Any,
    name: str,
) -> str | None:
    """Return a plain SSM parameter value, or ``None`` when it cannot be read."""
    if not name.strip():
        return None

    try:
        value = client.get_parameter(Name=name).get("Parameter", {}).get("Value")
        return value if isinstance(value, str) and value.strip() else None
    except (ClientError, BotoCoreError):
        return None


__all__ = ["get_parameter_value"]
