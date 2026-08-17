"""Resolve and validate CloudFormation installer templates."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import Any

from lza_workbench.core.installer_template import (
    INSTALLER_TEMPLATE_FILENAME,
    PACKAGED_INSTALLER_VERSION,
    download_installer_template,
)
from lza_workbench.errors import LzaError
from lza_workbench.installer.versions import normalize_lza_version
from lza_workbench.utils.output import print_info, print_notice
from lza_workbench.workspace.models import WorkspaceConfig


def resolve_installer_template(
    workspace_dir: Path, config: WorkspaceConfig, dry_run: bool
) -> Path:
    """Locate a local installer template or download it into the workspace."""
    installer_dir = workspace_dir / config.installer.local_path
    template_path = installer_dir / INSTALLER_TEMPLATE_FILENAME

    if not template_path.exists():
        if dry_run:
            print_info(
                f"Template {INSTALLER_TEMPLATE_FILENAME} not found locally. "
                "Would download during execution.",
                dim=True,
            )
            packaged = Path(
                str(
                    files("lza_workbench.resources.installer")
                    / INSTALLER_TEMPLATE_FILENAME
                )
            )
            if (
                normalize_lza_version(config.lza.version)
                == normalize_lza_version(PACKAGED_INSTALLER_VERSION)
                and packaged.exists()
            ):
                return packaged
            return template_path

        print_notice(f"Downloading LZA installer template ({config.lza.version})...")
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
