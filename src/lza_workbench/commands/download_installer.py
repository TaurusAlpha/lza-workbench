"""Download LZA installer CloudFormation template into customer workspace."""

from __future__ import annotations

import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from lza_workbench.core.workspace import (
    WORKSPACE_CONFIG_FILE,
    WORKSPACE_STATE_FILE,
    load_workspace_config,
    load_workspace_state,
    resolve_workspace_dir,
    write_workspace_state,
)

console = Console()

TEMPLATE_FILENAME = "AWSAccelerator-InstallerStack.template"
BASE_URL = "https://s3.amazonaws.com/solutions-reference/landing-zone-accelerator-on-aws"
LOCAL_PACKAGED_TEMPLATE = Path(__file__).parent.parent / "config" / TEMPLATE_FILENAME


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
    return f"{BASE_URL}/{norm_version}/{TEMPLATE_FILENAME}"


def run_download_installer(
    *,
    lza_version: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    interactive: bool = False,
    target_dir: Path | None = None,
) -> Path:
    """Download LZA installer CloudFormation template into workspace installer directory."""
    workspace_dir = resolve_workspace_dir(target_dir)
    config = load_workspace_config(workspace_dir / WORKSPACE_CONFIG_FILE)
    state = load_workspace_state(workspace_dir / WORKSPACE_STATE_FILE)

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
        console.print("[bold]Dry run: lza installer download[/bold]")
        console.print(f"Workspace: {workspace_dir}")
        console.print(f"LZA Version: {norm_version}")
        console.print(f"Template URL: {template_url}")
        console.print(f"Destination: {template_path}")
        console.print(
            f"Anonymous Data Sharing: {'Enabled' if anonymous_data_enabled else 'Disabled'}"
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

    template_content = _fetch_template_content(template_url)
    modified_content = _configure_anonymous_data(
        template_content, enable=anonymous_data_enabled
    )

    template_path.write_text(modified_content, encoding="utf-8")

    now = datetime.now(UTC)
    state.updated_at = now
    state.installer_downloaded_at = now
    state.installer_template_version = norm_version

    write_workspace_state(workspace_dir / WORKSPACE_STATE_FILE, state)

    console.print(f"[bold green]Downloaded LZA installer template ({norm_version})[/bold green]")
    console.print(f"Workspace: {workspace_dir}")
    console.print(f"Saved to: {template_path}")
    console.print(
        f"Anonymous Data Sharing: {'Enabled' if anonymous_data_enabled else 'Disabled'}"
    )

    return template_path


def _fetch_template_content(url: str) -> str:
    """Fetch CloudFormation template content from URL with fallback to local packaged template."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LZA-Workbench/0.6.0"})
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read().decode("utf-8")
    except Exception as exc:
        if LOCAL_PACKAGED_TEMPLATE.exists():
            return LOCAL_PACKAGED_TEMPLATE.read_text(encoding="utf-8")
        raise typer.BadParameter(
            f"Unable to download installer template from {url} and no local template was found."
        ) from exc


def _configure_anonymous_data(content: str, enable: bool) -> str:
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
