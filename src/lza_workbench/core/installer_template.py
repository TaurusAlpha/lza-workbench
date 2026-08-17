"""Download, resolve, and configure the LZA installer CloudFormation template."""

from __future__ import annotations

import json
import urllib.request
from importlib.resources import files
from pathlib import Path
from typing import Any

from lza_workbench.errors import LzaError
from lza_workbench.installer.versions import normalize_lza_version
from lza_workbench.utils.output import print_info

PACKAGED_INSTALLER_VERSION = "v1.16.0"
INSTALLER_TEMPLATE_FILENAME = "AWSAccelerator-InstallerStack.template"
INSTALLER_TEMPLATE_URL_TEMPLATE = (
    "https://s3.amazonaws.com/solutions-reference/landing-zone-accelerator-on-aws/"
    "{version}/{filename}"
)
LOCAL_PACKAGED_INSTALLER_TEMPLATE = Path(
    str(files("lza_workbench.resources.installer") / INSTALLER_TEMPLATE_FILENAME)
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
        LzaError: If the template cannot be downloaded and no fallback is available.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LZA-Workbench"})
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read().decode("utf-8")
    except Exception as exc:
        if fallback_version is not None:
            norm_requested = normalize_lza_version(fallback_version)
            norm_packaged = normalize_lza_version(PACKAGED_INSTALLER_VERSION)
            if norm_requested == norm_packaged:
                if fallback_path is not None and fallback_path.is_file():
                    return fallback_path.read_text(encoding="utf-8")
                raise LzaError(
                    f"Unable to download installer template from {url} and packaged fallback "
                    f"template for version {fallback_version} was not found at {fallback_path}."
                ) from exc

            raise LzaError(
                f"Unable to download installer template for {fallback_version} from {url} and no "
                f"local fallback template is available for this version (packaged version: "
                f"{PACKAGED_INSTALLER_VERSION})."
            ) from exc

        raise LzaError(
            f"Unable to download installer template from {url} and fallback is disabled."
        ) from exc


def download_installer_template(version: str, local_path: Path | None = None) -> Path:
    """Download the installer CloudFormation template for a specific LZA version.

    Args:
        version: The LZA version to download the installer template for.
    """
    url = INSTALLER_TEMPLATE_URL_TEMPLATE.format(
        version=version, filename=INSTALLER_TEMPLATE_FILENAME
    )
    template_content = resolve_installer_template(url, fallback_version=version)
    if local_path is None:
        local_path = Path.cwd() / INSTALLER_TEMPLATE_FILENAME
    local_path.write_text(template_content, encoding="utf-8")
    print_info(f"Downloaded installer template for version {version} to {local_path}")
    return local_path


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
