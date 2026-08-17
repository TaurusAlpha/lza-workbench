"""CLI command and presentation for uploading LZA configuration."""

from __future__ import annotations

from pathlib import Path

import typer

from lza_workbench.cli import params
from lza_workbench.cli.presentation import (
    print_diff_summary,
    print_dry_run_header,
    print_kv,
    print_success,
)
from lza_workbench.workflows.config_upload import (
    ConfigUploadResult,
    upload_configuration_workflow,
)


def render_config_upload_result(result: ConfigUploadResult) -> None:
    """Render the results of a configuration upload workflow."""
    if result.dry_run:
        print_dry_run_header("lza config upload")
        print_kv("Workspace", result.workspace_dir)
        print_kv("Source Directory", result.config_dir)
        print_kv("Local Zip Path", result.zip_path)
        print_kv("S3 Target", f"s3://{result.s3_bucket}/{result.s3_key}")
        print_kv("AWS Profile", result.aws_profile)
        print_kv("AWS Region", result.aws_region)
        return

    print_success("Packaged and uploaded LZA configuration")
    print_kv("Workspace", result.workspace_dir)
    print_kv("Zip archive", result.zip_path)
    print_kv("Destination", f"s3://{result.s3_bucket}/{result.s3_key}")
    print_diff_summary(
        result.diff_result.added,
        result.diff_result.modified,
        result.diff_result.removed,
    )


def config_upload_command(
    dry_run: params.DryRun = False,
    interactive: bool = False,
    target_dir: Path | None = None,
) -> Path:
    """Upload LZA configuration to configured repository destination."""
    result = upload_configuration_workflow(
        target_dir=target_dir,
        dry_run=dry_run,
        bucket_resolver=(lambda: typer.prompt("S3 bucket name for configuration"))
        if interactive
        else None,
    )
    render_config_upload_result(result)
    return result.zip_path
