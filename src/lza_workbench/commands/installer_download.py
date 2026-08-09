"""Download LZA installer CloudFormation template into customer workspace."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import typer

from lza_workbench.core.installer_template import (
    INSTALLER_TEMPLATE_FILENAME,
    INSTALLER_TEMPLATE_URL_TEMPLATE,
    configure_anonymous_data,
    resolve_installer_template,
)
from lza_workbench.core.workspace import (
    WORKSPACE_STATE_FILE,
    WorkspaceReadinessLevel,
    load_workspace_context,
    write_workspace_state,
)
from lza_workbench.utils.output import (
    print_dry_run_header,
    print_kv,
    print_success,
)

TEMPLATE_FILENAME = INSTALLER_TEMPLATE_FILENAME


def normalize_lza_version(version: str) -> str:
    """Format LZA version string into standard version format (e.g. v1.16.0 or latest)."""
    cleaned = version.strip()
    if not cleaned or cleaned.lower() == "latest":
        return "latest"
    if not cleaned.lower().startswith("v"):
        return f"v{cleaned}"
    return cleaned


def resolve_template_url(version: str) -> str:
    """Build S3 solution template URL for the given LZA version."""
    norm_version = normalize_lza_version(version)
    return INSTALLER_TEMPLATE_URL_TEMPLATE.format(
        version=norm_version, filename=INSTALLER_TEMPLATE_FILENAME
    )


def run_download_installer(
    *,
    lza_version: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    interactive: bool = False,
    target_dir: Path | None = None,
) -> Path:
    """Download LZA installer CloudFormation template into workspace installer directory."""
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED)
    workspace_dir, config, state = ctx.workspace_dir, ctx.config, ctx.state

    raw_version = (lza_version or "").strip() or (config.lza.version or "").strip()
    if not raw_version and interactive:
        raw_version = typer.prompt("LZA version to download", default="v1.16.0").strip()
    if not raw_version:
        raw_version = "v1.16.0"

    norm_version = normalize_lza_version(raw_version)
    template_url = resolve_template_url(norm_version)

    installer_dir = workspace_dir / config.installer.local_path
    template_path = installer_dir / TEMPLATE_FILENAME
    anonymous_data_enabled = config.installer.options.anonymous_data

    if dry_run:
        print_dry_run_header("lza installer download")
        print_kv("Workspace", workspace_dir)
        print_kv("LZA Version", norm_version)
        print_kv("Template URL", template_url)
        print_kv("Destination", template_path)
        print_kv(
            "Anonymous Data Sharing",
            "Enabled" if anonymous_data_enabled else "Disabled",
        )
        return template_path

    if template_path.exists() and not force:
        if interactive:
            confirm = typer.confirm(
                f"Installer template {template_path.name} already exists. Overwrite?"
            )
            if not confirm:
                raise typer.Abort()
        else:
            raise typer.BadParameter(
                f"Installer template already exists: {template_path}. Use --force to overwrite."
            )

    installer_dir.mkdir(parents=True, exist_ok=True)

    template_content = resolve_installer_template(template_url, fallback_version=norm_version)
    modified_content = configure_anonymous_data(template_content, enable=anonymous_data_enabled)

    template_path.write_text(modified_content, encoding="utf-8")

    now = datetime.now(UTC)
    state.updated_at = now
    state.installer_downloaded_at = now
    state.installer_template_version = norm_version

    write_workspace_state(workspace_dir / WORKSPACE_STATE_FILE, state)

    print_success(f"Downloaded LZA installer template ({norm_version})")
    print_kv("Workspace", workspace_dir)
    print_kv("Saved to", template_path)
    print_kv(
        "Anonymous Data Sharing",
        "Enabled" if anonymous_data_enabled else "Disabled",
    )

    return template_path
