"""AWS Organizations service adapter for account discovery."""

from __future__ import annotations

from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from lza_workbench.errors import LzaError


def list_organization_accounts(*, client: Any) -> list[dict[str, str]]:
    accounts: list[dict[str, str]] = []
    try:
        paginator = client.get_paginator("list_accounts")
        for page in paginator.paginate():
            for acc in page.get("Accounts", []):
                if acc.get("Status") == "ACTIVE":
                    accounts.append(
                        {
                            "Id": str(acc.get("Id", "")),
                            "Name": str(acc.get("Name", "")),
                            "Email": str(acc.get("Email", "")),
                            "Status": str(acc.get("Status", "")),
                        }
                    )
    except (ClientError, BotoCoreError) as exc:
        raise LzaError(f"Failed to list organization accounts: {exc}") from exc

    return accounts


__all__ = ["list_organization_accounts"]
