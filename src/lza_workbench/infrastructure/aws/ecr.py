"""Thin AWS ECR service adapter."""

from __future__ import annotations

from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from lza_workbench.errors import LzaError


def delete_repository(
    *,
    client: Any,
    repository_name: str,
    force: bool = True,
) -> None:
    """Delete an ECR repository and optionally its contained images."""
    clean_name = (repository_name or "").strip()
    if not clean_name:
        raise LzaError("Repository name must not be empty")

    try:
        client.delete_repository(repositoryName=clean_name, force=force)
    except (ClientError, BotoCoreError) as exc:
        raise LzaError(f"Failed to delete ECR repository '{clean_name}': {exc}") from exc


__all__ = ["delete_repository"]
