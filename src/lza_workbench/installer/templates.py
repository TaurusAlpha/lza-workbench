"""Download, resolve, configure, and validate LZA installer CloudFormation templates."""

from __future__ import annotations

import json
import urllib.request
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lza_workbench.errors import LzaError
from lza_workbench.installer.versions import (
    PACKAGED_INSTALLER_VERSION,
    normalize_lza_version,
)

if TYPE_CHECKING:
    from lza_workbench.workspace.schema import WorkspaceConfig

INSTALLER_TEMPLATE_FILENAME = "AWSAccelerator-InstallerStack.template"
INSTALLER_TEMPLATE_URL_TEMPLATE = (
    "https://s3.amazonaws.com/solutions-reference/landing-zone-accelerator-on-aws/"
    "{version}/{filename}"
)
LOCAL_PACKAGED_INSTALLER_TEMPLATE = Path(
    str(
        files("lza_workbench.resources.installer_templates")
        / PACKAGED_INSTALLER_VERSION
        / INSTALLER_TEMPLATE_FILENAME
    )
)


def download_installer_template_content(
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
        local_path: The local filesystem path to write the downloaded template to.
    """
    url = INSTALLER_TEMPLATE_URL_TEMPLATE.format(
        version=version, filename=INSTALLER_TEMPLATE_FILENAME
    )
    template_content = download_installer_template_content(url, fallback_version=version)
    if local_path is None:
        local_path = Path.cwd() / INSTALLER_TEMPLATE_FILENAME
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(template_content, encoding="utf-8")
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


def resolve_installer_template(
    workspace_dir: Path, config: WorkspaceConfig, dry_run: bool = False
) -> Path:
    """Locate a local installer template or download it into the workspace."""
    installer_dir = workspace_dir / config.installer.local_path
    template_path = installer_dir / INSTALLER_TEMPLATE_FILENAME

    if not template_path.exists():
        if dry_run:
            if (
                normalize_lza_version(config.lza.version)
                == normalize_lza_version(PACKAGED_INSTALLER_VERSION)
                and LOCAL_PACKAGED_INSTALLER_TEMPLATE.exists()
            ):
                return LOCAL_PACKAGED_INSTALLER_TEMPLATE
            return template_path

        template_path = download_installer_template(
            version=config.lza.version,
            local_path=template_path,
        )

    return template_path


def inspect_template_parameters(template_path: Path) -> dict[str, dict[str, Any]]:
    """Return parameter schema definitions from a JSON installer template."""
    if not template_path.exists():
        return {}

    try:
        data = json.loads(template_path.read_text(encoding="utf-8"))
        return data.get("Parameters", {})
    except (OSError, json.JSONDecodeError):
        return {}


def validate_parameters_against_schema(
    resolved_params: dict[str, str], schema: dict[str, dict[str, Any]]
) -> None:
    """Reject parameter values excluded by the installer template schema."""
    if not schema:
        return

    for key, value in resolved_params.items():
        if key not in schema:
            continue

        allowed = schema[key].get("AllowedValues")
        if allowed and value not in allowed:
            raise LzaError(
                f"Invalid parameter value '{value}' for {key}. "
                f"Allowed values are: {', '.join(allowed)}"
            )
