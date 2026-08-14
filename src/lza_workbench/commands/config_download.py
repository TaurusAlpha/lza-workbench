"""Download customer aws-accelerator-config zip archive from S3 into workspace root and extract."""

from __future__ import annotations

from pathlib import Path

import typer

from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.aws.s3 import download_s3_archive
from lza_workbench.config.archive import ConfigDiffResult, extract_zip_to_workspace
from lza_workbench.config.state import record_config_download
from lza_workbench.config.transfer import resolve_configuration_archive_location
from lza_workbench.core.errors import LzaError
from lza_workbench.utils.output import (
    print_diff_summary,
    print_dry_run_header,
    print_kv,
    print_success,
)
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context
from lza_workbench.workspace.state import (
    write_workspace_state,
)


def run_download_config(
    *,
    dry_run: bool = False,
    force: bool = False,
    extract: bool = True,
    interactive: bool = False,
    target_dir: Path | None = None,
) -> Path:
    """Download aws-accelerator-config zip archive from S3 into workspace root and extract."""
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED)
    workspace_dir, config, state = ctx.workspace_dir, ctx.config, ctx.state

    config_dir = workspace_dir / config.configuration.local_path
    archive_location = resolve_configuration_archive_location(
        workspace_dir=workspace_dir,
        repository=config.configuration.repository,
        prompt_for_bucket=(lambda: typer.prompt("S3 bucket name for configuration"))
        if interactive
        else None,
    )
    profile = config.aws.profile or ""
    region = config.aws.region
    zip_path = archive_location.zip_path

    if dry_run:
        print_dry_run_header("lza config download")
        print_kv("Workspace", workspace_dir)
        print_kv("S3 Source", f"s3://{archive_location.bucket}/{archive_location.key}")
        print_kv("AWS Profile", profile)
        print_kv("AWS Region", region)
        print_kv("Local Zip Path", zip_path)
        print_kv("Extraction Target", workspace_dir)
        return config_dir

    if config_dir.exists() and any(config_dir.iterdir()) and not force:
        if interactive:
            confirm = typer.confirm(
                f"Local configuration directory {config_dir} is not empty. Overwrite local files?"
            )
            if not confirm:
                raise typer.Abort()
        else:
            raise LzaError(
                f"Local configuration directory is not empty: {config_dir}. "
                "Use --force to overwrite."
            )

    exclude_dirs = set(config.configuration.packaging.exclude.directories)
    exclude_files = set(config.configuration.packaging.exclude.files)

    aws_context = resolve_aws_execution_context(config.aws, require_identity=True)
    download_s3_archive(
        s3_bucket=archive_location.bucket,
        s3_key=archive_location.key,
        prefix=config.configuration.repository.prefix.strip(),
        zip_path=zip_path,
        factory=aws_context.factory,
    )

    if extract:
        diff_result = extract_zip_to_workspace(
            zip_path=zip_path,
            config_dir=config_dir,
            exclude_dirs=exclude_dirs,
            exclude_files=exclude_files,
        )
    else:
        diff_result = ConfigDiffResult(added=[zip_path.name], modified=[], removed=[])

    record_config_download(
        state,
        zip_path=zip_path,
        config_dir=config_dir,
        exclude_dirs=exclude_dirs,
        exclude_files=exclude_files,
        diff_result=diff_result,
    )

    write_workspace_state(workspace_dir, state)

    action_str = "Downloaded and extracted " if extract else "Downloaded "
    print_success(f"{action_str}LZA configuration")
    print_kv("Workspace", workspace_dir)
    print_kv("Source", f"s3://{archive_location.bucket}/{archive_location.key}")
    print_kv("Zip archive", zip_path)
    print_kv("Extracted to", config_dir)

    print_diff_summary(diff_result.added, diff_result.modified, diff_result.removed)

    return config_dir
