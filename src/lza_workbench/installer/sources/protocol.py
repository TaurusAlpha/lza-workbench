"""Installer source provider protocol."""

from __future__ import annotations

from typing import Any, Protocol


class InstallerSourceProvider(Protocol):
    """Protocol for installer source providers."""

    def inspect_prerequisites(self) -> dict[str, Any]:
        """Inspect prerequisites for this installer source."""
        ...

    def validate_readiness(self) -> bool:
        """Validate readiness for deployment."""
        ...


__all__ = ["InstallerSourceProvider"]
