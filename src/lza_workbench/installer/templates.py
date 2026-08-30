"""Download, resolve, configure, and validate LZA installer CloudFormation templates."""

from __future__ import annotations

import json
import re
import shutil
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
    normalized_version = normalize_lza_version(version)
    url = INSTALLER_TEMPLATE_URL_TEMPLATE.format(
        version=normalized_version, filename=INSTALLER_TEMPLATE_FILENAME
    )
    template_content = download_installer_template_content(
        url, fallback_version=normalized_version
    )
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


def extract_template_version(content: str) -> str | None:
    """Extract LZA version from template description if present."""
    match = re.search(r"Version\s+v?([0-9]+\.[0-9]+\.[0-9]+)", content)
    if match:
        return f"v{match.group(1)}"
    return None


def backup_installer_template(
    installer_dir: Path, template_path: Path, fallback_version: str
) -> Path | None:
    """Back up existing template file into a versioned subdirectory under backups/."""
    if not template_path.exists():
        return None

    try:
        content = template_path.read_text(encoding="utf-8")
        version_str = extract_template_version(content) or fallback_version
    except OSError:
        version_str = fallback_version

    backup_dir = installer_dir / "backups" / version_str
    backup_path = backup_dir / INSTALLER_TEMPLATE_FILENAME
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template_path, backup_path)
    except OSError as exc:
        raise LzaError(f"Unable to back up installer template to {backup_path}: {exc}") from exc
    return backup_path


def resolve_installer_template(
    workspace_dir: Path, config: WorkspaceConfig, dry_run: bool = False
) -> Path:
    """Resolve the configured installer template into a local usable template path."""
    template_config = config.installer.stack_template
    if template_config.source == "local":
        if not template_config.path:
            raise LzaError("installer.stack_template.path is required when source is 'local'.")
        configured_path = Path(template_config.path).expanduser()
        template_path = (
            configured_path
            if configured_path.is_absolute()
            else (workspace_dir / configured_path).resolve()
        )
        if not template_path.is_file():
            raise LzaError(f"Configured local installer template was not found: {template_path}")
    elif template_config.source in {"git", "s3"}:
        raise LzaError(
            f"Installer template source '{template_config.source}' is not supported yet. "
            "Use source 'amazon' or 'local'."
        )
    else:
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
        elif not dry_run:
            # Check if version has changed
            try:
                existing_content = template_path.read_text(encoding="utf-8")
                existing_ver = extract_template_version(existing_content)
                if existing_ver and normalize_lza_version(existing_ver) != normalize_lza_version(
                    config.lza.version
                ):
                    backup_installer_template(installer_dir, template_path, existing_ver)
                    template_path = download_installer_template(
                        version=config.lza.version,
                        local_path=template_path,
                    )
            except OSError as exc:
                raise LzaError(
                    f"Unable to inspect installer template {template_path}: {exc}"
                ) from exc

    # Configure anonymous data sharing in template if modified/disabled
    if template_path.exists() and not dry_run:
        try:
            content = template_path.read_text(encoding="utf-8")
            enable_anon = config.installer.options.anonymous_data
            configured = configure_anonymous_data(content, enable_anon)
            if configured != content:
                template_path.write_text(configured, encoding="utf-8")
        except OSError as exc:
            raise LzaError(
                f"Unable to configure installer template {template_path}: {exc}"
            ) from exc

    return template_path



def inspect_template_parameters(template_path: Path) -> dict[str, dict[str, Any]]:
    """Return parameter schema definitions from a JSON installer template."""
    if not template_path.is_file():
        raise LzaError(f"Installer template was not found: {template_path}")

    try:
        data = json.loads(template_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise LzaError(f"Unable to read installer template {template_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise LzaError(f"Installer template is not valid JSON: {template_path}: {exc}") from exc

    parameters = data.get("Parameters")
    if not isinstance(parameters, dict):
        raise LzaError(f"Installer template has no Parameters object: {template_path}")
    return parameters


def validate_parameters_against_schema(
    resolved_params: dict[str, str], schema: dict[str, dict[str, Any]]
) -> None:
    """Reject parameter values excluded by the installer template schema."""
    if not schema:
        return

    for key, definition in schema.items():
        if key not in resolved_params:
            if "Default" not in definition:
                raise LzaError(
                    f"Installer template parameter '{key}' has no configured value or "
                    "template default."
                )
            continue

        value = resolved_params[key]

        allowed = definition.get("AllowedValues")
        if allowed and value not in allowed:
            raise LzaError(
                f"Invalid parameter value '{value}' for {key}. "
                f"Allowed values are: {', '.join(allowed)}"
            )

        pattern = definition.get("AllowedPattern")
        if pattern and not re.fullmatch(pattern, value):
            raise LzaError(
                f"Invalid parameter value '{value}' for {key}. "
                f"It must match template pattern: {pattern}"
            )
