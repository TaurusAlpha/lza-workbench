"""Thin AWS DynamoDB service adapter."""

from __future__ import annotations

from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from lza_workbench.errors import LzaError


def delete_table(
    *,
    client: Any,
    table_name: str,
) -> None:
    """Delete a DynamoDB table."""
    clean_name = (table_name or "").strip()
    if not clean_name:
        raise LzaError("Table name must not be empty")

    try:
        client.delete_table(TableName=clean_name)
    except (ClientError, BotoCoreError) as exc:
        raise LzaError(f"Failed to delete DynamoDB table '{clean_name}': {exc}") from exc


__all__ = ["delete_table"]
