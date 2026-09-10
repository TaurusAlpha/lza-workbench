"""Configuration remote provider protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class ConfigurationRemote(Protocol):
    """Protocol for configuration remotes (S3, CodeCommit, Git)."""

    def inspect(self) -> dict[str, Any]:
        """Inspect remote configuration status."""
        ...

    def push(self, local_path: Path, **kwargs: Any) -> Any:
        """Push configuration to the remote."""
        ...

    def pull(self, local_path: Path, **kwargs: Any) -> Any:
        """Pull configuration from the remote."""
        ...


__all__ = ["ConfigurationRemote"]
