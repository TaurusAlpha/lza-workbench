"""Normalize LZA release versions and installer repository branches."""

from __future__ import annotations

PACKAGED_INSTALLER_VERSION = "v1.16.0"



def normalize_lza_version(version: str | None) -> str:
    """Return a canonical LZA version: ``latest`` or ``vX.Y.Z``.

    ``latest``, ``main``, and ``master`` all represent the current main branch.
    Release branch references are accepted to keep configuration and deployed
    CloudFormation parameters comparable.
    """
    cleaned = (version or "").strip()
    if not cleaned:
        return "latest"

    if cleaned.lower().startswith("release/"):
        cleaned = cleaned[len("release/") :].strip()

    if cleaned.lower() in {"latest", "main", "master"}:
        return "latest"
    if cleaned.lower().startswith("v"):
        return f"v{cleaned[1:]}"
    return f"v{cleaned}"


def version_to_branch(version: str | None) -> str:
    """Convert an LZA version into its official installer source branch."""
    normalized = normalize_lza_version(version)
    return "main" if normalized == "latest" else f"release/{normalized}"


def branch_to_version(branch: str | None) -> str:
    """Extract a canonical LZA version from an installer source branch."""
    cleaned = (branch or "").strip()
    if not cleaned:
        return "Unknown"
    return normalize_lza_version(cleaned)
