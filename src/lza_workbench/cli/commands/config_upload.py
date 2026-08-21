"""CLI command and presentation for uploading LZA configuration."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.cli import params
from lza_workbench.cli.commands.config_push import (
    config_push_command,
    render_config_push_result,
)
from lza_workbench.workflows.config_push import ConfigUploadResult

render_config_upload_result = render_config_push_result


def config_upload_command(
    dry_run: params.DryRun = False,
    interactive: bool = False,
    target_dir: Path | None = None,
) -> Path | None:
    """Upload LZA configuration to configured repository destination."""
    result: ConfigUploadResult = config_push_command(
        dry_run=dry_run,
        interactive=interactive,
        target_dir=target_dir,
    )
    return result.zip_path

