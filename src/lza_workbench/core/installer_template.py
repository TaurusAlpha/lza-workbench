"""Download, resolve, and configure the LZA installer CloudFormation template."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

console = Console()

PACKAGED_INSTALLER_VERSION = "v1.16.0"
INSTALLER_TEMPLATE_FILENAME = "AWSAccelerator-InstallerStack.template"
INSTALLER_TEMPLATE_URL_TEMPLATE = (
    "https://s3.amazonaws.com/solutions-reference/landing-zone-accelerator-on-aws/"
    "{version}/{filename}"
)
LOCAL_PACKAGED_INSTALLER_TEMPLATE = (
    Path(__file__).parent.parent / "config" / INSTALLER_TEMPLATE_FILENAME
)


def resolve_installer_template(
    url: str,
    fallback_version: str | None = None,
    fallback_path: Path | None = LOCAL_PACKAGED_INSTALLER_TEMPLATE,
) -> str:
    """Download the installer CloudFormation template from AWS with fallback.

    Args:
        url: The official AWS S3 URL for the installer template.
        fallback_version: The LZA version requested for fallback (if None, fallback is disabled).
        fallback_path: Path to the local packaged template fallback (representing v1.16.0).

    Returns:
        The downloaded or fallback CloudFormation template content as a string.

    Raises:
        typer.BadParameter: If the template cannot be downloaded and no fallback is available.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LZA-Workbench"})
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read().decode("utf-8")
    except Exception as exc:
        if fallback_version is not None and fallback_path is not None and fallback_path.is_file():
            return fallback_path.read_text(encoding="utf-8")

        raise typer.BadParameter(
            f"Unable to download installer template from {url} and no local template was found."
        ) from exc


def configure_anonymous_data(content: str, enable: bool) -> str:
    """Parse JSON template and update anonymous data sharing setting in Mappings."""
    try:
        data: dict[str, Any] = json.loads(content)
        mappings = data.get("Mappings", {})
        for map_val in mappings.values():
            if isinstance(map_val, dict) and "SendAnonymizedData" in map_val:
                map_val["SendAnonymizedData"]["Data"] = "Yes" if enable else "No"
        return json.dumps(data, indent=2) + "\n"
    except json.JSONDecodeError:
        return content
