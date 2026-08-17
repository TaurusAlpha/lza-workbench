"""Compatibility wrapper for configuration download command (to be removed in Step 16)."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.cli.commands.config_download import config_download_command


def run_download_config(
    *,
    dry_run: bool = False,
    force: bool = False,
    extract: bool = True,
    interactive: bool = False,
    target_dir: Path | None = None,
) -> Path:
    """Download aws-accelerator-config zip archive from S3 into workspace root and extract."""
    return config_download_command(
        dry_run=dry_run,
        force=force,
        extract=extract,
        interactive=interactive,
        target_dir=target_dir,
    )
