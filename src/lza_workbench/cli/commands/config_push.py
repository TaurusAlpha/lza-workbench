"""CLI command and presentation for synchronizing LZA configuration to remote repositories."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.cli import params
from lza_workbench.cli.output import (
    print_diff_summary,
    print_dry_run_header,
    print_kv,
    print_success,
)
from lza_workbench.workflows.config_push import (
    ConfigPushResult,
    push_configuration_workflow,
)


def render_config_push_result(result: ConfigPushResult) -> None:
    """Render the results of a configuration push workflow."""
    if result.dry_run:
        print_dry_run_header("lza config push")
        print_kv("Workspace", result.workspace_dir)
        print_kv("Source Directory", result.config_dir)
        print_kv("Repository Type", result.repository_type)

        if result.repository_type == "s3":
            print_kv("Local Zip Path", result.zip_path)
            print_kv("S3 Target", f"s3://{result.s3_bucket}/{result.s3_key}")
            print_kv("AWS Profile", result.aws_profile)
            print_kv("AWS Region", result.aws_region)
        else:
            print_kv("Remote URL", result.git_remote_url)
            print_kv("Branch", result.git_branch)
            print_kv("Commit", result.git_commit)
            print_kv("Tracked Files", result.files_count)
        return

    if result.repository_type == "s3":
        print_success("Packaged and uploaded LZA configuration")
        print_kv("Workspace", result.workspace_dir)
        print_kv("Zip archive", result.zip_path)
        print_kv("Destination", f"s3://{result.s3_bucket}/{result.s3_key}")
        if result.diff_result:
            print_diff_summary(
                result.diff_result.added,
                result.diff_result.modified,
                result.diff_result.removed,
            )
    else:
        print_success(f"Pushed LZA configuration to {result.repository_type} repository")
        print_kv("Workspace", result.workspace_dir)
        print_kv("Remote URL", result.git_remote_url)
        print_kv("Branch", result.git_branch)
        print_kv("Commit", result.git_commit)
        print_kv("Tracked Files", result.files_count)


def config_push_command(
    dry_run: params.DryRun = False,
    interactive: bool = False,
    target_dir: Path | None = None,
) -> ConfigPushResult:
    """Synchronize LZA configuration to configured repository destination."""
    result = push_configuration_workflow(
        target_dir=target_dir,
        dry_run=dry_run,
    )
    render_config_push_result(result)
    return result
