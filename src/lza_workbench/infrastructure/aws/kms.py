"""Thin AWS KMS service adapter."""

from __future__ import annotations

from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from lza_workbench.errors import LzaError


def schedule_key_deletion(
    *,
    client: Any,
    key_id: str,
    pending_window_days: int = 7,
) -> None:
    clean_key = (key_id or "").strip()
    if not clean_key:
        raise LzaError("KMS Key ID must not be empty")

    try:
        client.schedule_key_deletion(KeyId=clean_key, PendingWindowInDays=pending_window_days)
    except (ClientError, BotoCoreError) as exc:
        raise LzaError(f"Failed to schedule deletion for KMS Key '{clean_key}': {exc}") from exc


def delete_alias(
    *,
    client: Any,
    alias_name: str,
) -> None:
    clean_alias = (alias_name or "").strip()
    if not clean_alias:
        raise LzaError("KMS alias name must not be empty")

    try:
        client.delete_alias(AliasName=clean_alias)
    except (ClientError, BotoCoreError) as exc:
        raise LzaError(f"Failed to delete KMS alias '{clean_alias}': {exc}") from exc


__all__ = [
    "delete_alias",
    "schedule_key_deletion",
]
