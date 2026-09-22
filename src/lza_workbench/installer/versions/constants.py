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
    normalized = normalize_lza_version(version)
    return "main" if normalized == "latest" else f"release/{normalized}"


def branch_to_version(branch: str | None) -> str:
    cleaned = (branch or "").strip()
    if not cleaned:
        return "Unknown"
    return normalize_lza_version(cleaned)


UNWANTED_LZA_VERSIONS: tuple[str, ...] = (
    "v1.0.0",
    "v1.0.1",
    "v1.0.2",
    "v1.1.0",
    "v1.1.1",
    "v1.1.2",
    "v1.2.0",
    "v1.2.1",
    "v1.2.2",
    "v1.3.0",
    "v1.3.1",
    "v1.3.2",
    "v1.4.0",
    "v1.4.1",
    "v1.4.2",
    "v1.5.0",
)


def is_unwanted_lza_version(version: str | None) -> bool:
    """Return True if the version is an old or unwanted LZA release (up to v1.5.0)."""
    normalized = normalize_lza_version(version)
    if normalized in UNWANTED_LZA_VERSIONS:
        return True
    if normalized.startswith("v"):
        parts = normalized[1:].split(".")
        try:
            nums = [int(p) for p in parts]
            if len(nums) >= 2:
                if nums[0] < 1:
                    return True
                if nums[0] == 1 and nums[1] < 5:
                    return True
                if nums[0] == 1 and nums[1] == 5 and (len(nums) == 2 or nums[2] == 0):
                    return True
        except ValueError:
            pass
    return False


__all__ = [
    "PACKAGED_INSTALLER_VERSION",
    "UNWANTED_LZA_VERSIONS",
    "branch_to_version",
    "is_unwanted_lza_version",
    "normalize_lza_version",
    "version_to_branch",
]
