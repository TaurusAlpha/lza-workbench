"""Compatibility wrapper for configuration upload command (to be removed in Step 16)."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.cli.commands.config_upload import config_upload_command


def run_upload_config(
    *,
    dry_run: bool = False,
    interactive: bool = False,
    target_dir: Path | None = None,
) -> Path:
    """Package aws-accelerator-config into zip, display change visibility, and upload to S3."""
    return config_upload_command(
        dry_run=dry_run,
        interactive=interactive,
        target_dir=target_dir,
    )
