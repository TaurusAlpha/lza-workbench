"""Download, resolve, configure, and validate LZA installer CloudFormation templates."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
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
    from lza_workbench.installer.schema import LzaInstaller
    from lza_workbench.workspace.schema import CustomerEnvironmentTarget, WorkspaceConfig

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
    """Download the installer CloudFormation template from AWS, falling back to local packaged templates."""
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
    normalized_version = normalize_lza_version(version)
    url = INSTALLER_TEMPLATE_URL_TEMPLATE.format(
        version=normalized_version, filename=INSTALLER_TEMPLATE_FILENAME
    )
    template_content = download_installer_template_content(url, fallback_version=normalized_version)
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


def _resolve_local_installer_template(workspace_dir: Path, template_path_str: str | None) -> Path:
    if not template_path_str:
        raise LzaError("installer.stack_template.path is required when source is 'local'.")
    configured_path = Path(template_path_str).expanduser()
    template_path = (
        configured_path
        if configured_path.is_absolute()
        else (workspace_dir / configured_path).resolve()
    )
    if not template_path.is_file():
        raise LzaError(f"Configured local installer template was not found: {template_path}")
    return template_path


def _resolve_amazon_installer_template(installer_dir: Path, version: str, dry_run: bool) -> Path:
    template_path = installer_dir / INSTALLER_TEMPLATE_FILENAME
    if not template_path.exists():
        if dry_run:
            if (
                normalize_lza_version(version) == normalize_lza_version(PACKAGED_INSTALLER_VERSION)
                and LOCAL_PACKAGED_INSTALLER_TEMPLATE.exists()
            ):
                return LOCAL_PACKAGED_INSTALLER_TEMPLATE
            return template_path

        return download_installer_template(version=version, local_path=template_path)

    if not dry_run:
        try:
            existing_content = template_path.read_text(encoding="utf-8")
            existing_ver = extract_template_version(existing_content)
            if existing_ver and normalize_lza_version(existing_ver) != normalize_lza_version(
                version
            ):
                backup_installer_template(installer_dir, template_path, existing_ver)
                template_path = download_installer_template(
                    version=version, local_path=template_path
                )
        except OSError as exc:
            raise LzaError(f"Unable to inspect installer template {template_path}: {exc}") from exc

    return template_path


def _apply_anonymous_data_setting(
    template_path: Path, enable_anon: bool, *, mutate_in_place: bool = True
) -> Path:
    try:
        content = template_path.read_text(encoding="utf-8")
        configured = configure_anonymous_data(content, enable_anon)
        if configured == content:
            return template_path
        if mutate_in_place:
            template_path.write_text(configured, encoding="utf-8")
            return template_path
        digest_prefix = hashlib.sha256(configured.encode("utf-8")).hexdigest()[:16]
        artifact_dir = Path(tempfile.gettempdir()) / "lza-workbench-installer-templates"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / f"{digest_prefix}-{INSTALLER_TEMPLATE_FILENAME}"
        artifact_path.write_text(configured, encoding="utf-8")
        return artifact_path
    except OSError as exc:
        raise LzaError(f"Unable to configure installer template {template_path}: {exc}") from exc


def resolve_installer_template(
    workspace_dir: Path,
    config: WorkspaceConfig | None = None,
    dry_run: bool = False,
    *,
    installer: LzaInstaller | None = None,
    environment_target: CustomerEnvironmentTarget | None = None,
) -> Path:
    resolved_installer = installer or (config.installer if config is not None else None)
    resolved_target = environment_target or (
        config.environment_target if config is not None else None
    )
    if resolved_installer is None or resolved_target is None:
        raise ValueError(
            "resolve_installer_template requires either config or (installer and environment_target)."
        )

    template_config = resolved_installer.stack_template
    if template_config.source == "local":
        template_path = _resolve_local_installer_template(workspace_dir, template_config.path)
    elif template_config.source in {"git", "s3"}:
        raise LzaError(
            f"Installer template source '{template_config.source}' is not supported yet. "
            "Use source 'amazon' or 'local'."
        )
    else:
        installer_dir = workspace_dir / resolved_installer.local_path
        template_path = _resolve_amazon_installer_template(
            installer_dir=installer_dir,
            version=resolved_target.lza.version,
            dry_run=dry_run,
        )

    # Configure anonymous data sharing in template; avoid mutating read-only or dry-run sources
    if template_path.exists():
        mutate_in_place = (
            not dry_run
            and template_config.source != "local"
            and template_path != LOCAL_PACKAGED_INSTALLER_TEMPLATE
        )
        template_path = _apply_anonymous_data_setting(
            template_path,
            resolved_installer.options.anonymous_data,
            mutate_in_place=mutate_in_place,
        )

    return template_path


def inspect_template_parameters(template_path: Path) -> dict[str, dict[str, Any]]:
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


def prepare_installer_template(
    *,
    config: WorkspaceConfig | None = None,
    installer: LzaInstaller | None = None,
    environment_target: CustomerEnvironmentTarget | None = None,
    workspace_dir: Path | None = None,
    template_path: Path | None = None,
    dry_run: bool = False,
) -> tuple[Path, dict[str, str]]:
    """Resolve, configure, and validate the installer template and its parameters."""
    from lza_workbench.installer.parameters import build_installer_cfn_parameters

    resolved_installer = installer or (config.installer if config is not None else None)
    resolved_target = environment_target or (
        config.environment_target if config is not None else None
    )
    if resolved_installer is None or resolved_target is None:
        raise ValueError(
            "prepare_installer_template requires either config or (installer and environment_target)."
        )

    if template_path is not None:
        resolved_template_path = (
            _apply_anonymous_data_setting(
                template_path,
                resolved_installer.options.anonymous_data,
                mutate_in_place=False,
            )
            if template_path.is_file()
            else template_path
        )
    elif workspace_dir is not None:
        resolved_template_path = resolve_installer_template(
            workspace_dir,
            config,
            dry_run=dry_run,
            installer=resolved_installer,
            environment_target=resolved_target,
        )
    else:
        raise LzaError(
            "Installer template preparation requires either template_path or workspace_dir."
        )

    schema = inspect_template_parameters(resolved_template_path)
    parameters = build_installer_cfn_parameters(
        config,
        schema=schema,
        installer=resolved_installer,
        environment_target=resolved_target,
    )
    validate_parameters_against_schema(parameters, schema)
    return resolved_template_path, parameters


__all__ = [
    "INSTALLER_TEMPLATE_FILENAME",
    "INSTALLER_TEMPLATE_URL_TEMPLATE",
    "LOCAL_PACKAGED_INSTALLER_TEMPLATE",
    "configure_anonymous_data",
    "download_installer_template",
    "download_installer_template_content",
    "inspect_template_parameters",
    "prepare_installer_template",
    "resolve_installer_template",
    "validate_parameters_against_schema",
]
