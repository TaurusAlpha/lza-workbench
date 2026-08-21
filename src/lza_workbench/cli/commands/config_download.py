"""CLI command and presentation for downloading LZA configuration."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.cli import params
from lza_workbench.cli.commands.config_pull import (
    config_pull_command,
    render_config_pull_result,
)
from lza_workbench.workflows.config_pull import ConfigDownloadResult

render_config_download_result = render_config_pull_result


def config_download_command(
    dry_run: params.DryRun = False,
    force: params.Force = False,
    extract: params.Extract = True,
    interactive: bool = False,
    target_dir: Path | None = None,
) -> Path:
    """Download LZA configuration from configured repository source."""
    result: ConfigDownloadResult = config_pull_command(
        dry_run=dry_run,
        force=force,
        extract=extract,
        interactive=interactive,
        target_dir=target_dir,
    )
    return result.config_dir
