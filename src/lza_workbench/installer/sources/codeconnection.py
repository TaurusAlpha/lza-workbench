"""CodeConnection installer source provider."""

from __future__ import annotations

from typing import Any

from lza_workbench.infrastructure.aws.codeconnections import inspect_codeconnection


class CodeConnectionInstallerSourceProvider:
    """CodeConnection source provider for LZA installer pipeline."""

    def __init__(
        self,
        *,
        connection_arn: str,
        codeconnections_client: Any = None,
    ) -> None:
        self.connection_arn = connection_arn
        self.codeconnections_client = codeconnections_client

    def inspect_prerequisites(self) -> dict[str, Any]:
        """Inspect CodeConnection status."""
        status = "UNKNOWN"
        exists = False
        if self.codeconnections_client:
            obs = inspect_codeconnection(
                client=self.codeconnections_client,
                connection_arn=self.connection_arn,
            )
            status = obs.status or "UNKNOWN"
            exists = obs.status not in {"NOT_FOUND", "NOT_SPECIFIED", None}

        return {
            "connection_arn": self.connection_arn,
            "status": status,
            "exists": exists,
        }

    def validate_readiness(self) -> bool:
        """Validate if the connection is available."""
        if not self.codeconnections_client:
            return True
        obs = inspect_codeconnection(
            client=self.codeconnections_client,
            connection_arn=self.connection_arn,
        )
        return obs.status == "AVAILABLE"


__all__ = ["CodeConnectionInstallerSourceProvider"]
