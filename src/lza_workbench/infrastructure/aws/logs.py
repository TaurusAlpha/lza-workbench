"""Thin AWS CloudWatch Logs service adapter."""

from __future__ import annotations

from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from lza_workbench.errors import LzaError


def delete_log_group(*, client: Any, log_group_name: str) -> None:
    clean_name = (log_group_name or "").strip()
    if not clean_name:
        raise LzaError("Log group name must not be empty")

    try:
        client.delete_log_group(logGroupName=clean_name)
    except (ClientError, BotoCoreError) as exc:
        raise LzaError(f"Failed to delete CloudWatch Log Group '{clean_name}': {exc}") from exc


__all__ = ["delete_log_group"]
