"""CLI command and presentation for synchronizing LZA configuration from remote repositories."""

from __future__ import annotations

from pathlib import Path

import typer

from lza_workbench.cli import params
from lza_workbench.cli.output import (
    print_diff_summary,
    print_dry_run_header,
    print_kv,
    print_success,
)
from lza_workbench.workflows.config_pull import (
    ConfigPullResult,
    pull_configuration_workflow,
)


def render_config_pull_result(result: ConfigPullResult) -> None:
    """Render the results of a configuration pull workflow."""
    if result.dry_run:
        print_dry_run_header("lza config pull")
        print_kv("Workspace", result.workspace_dir)
        print_kv("Destination Directory", result.config_dir)
        print_kv("Repository Type", result.repository_type)

        if result.repository_type == "s3":
            print_kv("S3 Source", f"s3://{result.s3_bucket}/{result.s3_key}")
            print_kv("AWS Profile", result.aws_profile)
            print_kv("AWS Region", result.aws_region)
            print_kv("Local Zip Path", result.zip_path)
            print_kv("Extraction Target", result.config_dir)
        else:
            print_kv("Remote URL", result.git_remote_url)
            print_kv("Branch", result.git_branch)
            if result.git_commit:
                print_kv("Commit", result.git_commit)
            if result.files_count is not None:
                print_kv("Tracked Files", result.files_count)
        return

    if result.repository_type == "s3":
        action_str = "Downloaded and extracted " if result.extracted else "Downloaded "
        print_success(f"{action_str}LZA configuration")
        print_kv("Workspace", result.workspace_dir)
        print_kv("Source", f"s3://{result.s3_bucket}/{result.s3_key}")
        print_kv("Zip archive", result.zip_path)
        if result.extracted:
            print_kv("Extracted to", result.config_dir)
        if result.diff_result:
            print_diff_summary(
                result.diff_result.added,
                result.diff_result.modified,
                result.diff_result.removed,
            )
    else:
        print_success(f"Pulled LZA configuration from {result.repository_type} repository")
        print_kv("Workspace", result.workspace_dir)
        print_kv("Remote URL", result.git_remote_url)
        print_kv("Branch", result.git_branch)
        print_kv("Commit", result.git_commit)
        print_kv("Tracked Files", result.files_count)
        if result.stashed_changes:
            print_kv("Local Changes", "Uncommitted changes were stashed")


def config_pull_command(
    dry_run: params.DryRun = False,
    force: params.Force = False,
    extract: params.Extract = True,
    interactive: bool = False,
    target_dir: Path | None = None,
) -> ConfigPullResult:
    """Synchronize LZA configuration from configured remote repository or S3."""
    overwrite_confirmed = False
    if interactive and not force and not dry_run:
        from lza_workbench.workspace.config import load_workspace_config
        from lza_workbench.workspace.paths import resolve_workspace_dir

        ws_dir = resolve_workspace_dir(target_dir)
        cfg = load_workspace_config(ws_dir)
        local_dir = ws_dir / cfg.configuration.local_path
        if local_dir.is_dir() and any(local_dir.iterdir()):
            confirm = typer.confirm(
                f"Local configuration directory {local_dir} is not empty. "
                "Overwrite or sync remote changes?"
            )
            if not confirm:
                raise typer.Abort()
            overwrite_confirmed = True

    result = pull_configuration_workflow(
        target_dir=target_dir,
        dry_run=dry_run,
        force=force,
        extract=extract,
        bucket_resolver=(lambda: typer.prompt("S3 bucket name for configuration"))
        if interactive
        else None,
        overwrite_confirmed=overwrite_confirmed,
    )
    render_config_pull_result(result)
    return result
