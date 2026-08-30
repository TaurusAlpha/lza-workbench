"""CLI command and presentation for configuration repository status."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.cli.output import (
    console,
    format_status,
    format_timestamp,
    print_info,
    print_kv,
    print_section,
    print_warning,
    render_workspace_header,
)
from lza_workbench.workflows.status_config import (
    ConfigurationStatusResult,
    get_config_status_workflow,
)


def _render_local_config(result: ConfigurationStatusResult) -> None:
    print_section(1, "Local Configuration")

    exists_str = "[green]Present[/green]" if result.config_dir_exists else "[red]Missing[/red]"
    print_kv("Local Config Path", f"{result.config_dir} ({exists_str})")

    if result.yaml_files:
        files_preview = ", ".join(result.yaml_files[:5])
        suffix = f" ... (+{len(result.yaml_files) - 5} more)" if len(result.yaml_files) > 5 else ""
        print_kv("YAML Config Files", f"{len(result.yaml_files)} files ({files_preview}{suffix})")
    else:
        print_kv("YAML Config Files", "0 files found", style="dim")

    if result.initialized_at:
        init_str = format_timestamp(result.initialized_at) or "Unknown"
        tmpl_str = result.template_name or "default"
        print_kv("Configuration Origin", f"Initialized from '{tmpl_str}' template ({init_str})")
    elif result.config_dir_exists:
        print_kv("Configuration Origin", "Imported / Unmanaged")

    if result.git_working_tree:
        gwt = result.git_working_tree
        print_kv("Git Branch", gwt.branch, bold_value=True)
        commit_str = gwt.commit or "No commits"
        if gwt.commit_subject:
            commit_str += f' ("{gwt.commit_subject}")'
        print_kv("HEAD Commit", commit_str)

        if gwt.has_uncommitted:
            suffix = "s" if gwt.uncommitted_count != 1 else ""
            print_kv(
                "Working Tree",
                f"Dirty ({gwt.uncommitted_count} uncommitted change{suffix})",
                style="yellow",
            )
        else:
            print_kv("Working Tree", "Clean", style="green")

        if result.git_sync_status:
            sync = result.git_sync_status
            print_kv("Remote Sync", format_status(sync.summary))


def _render_repository_settings(result: ConfigurationStatusResult) -> None:
    console.print()
    print_section(2, "Repository Settings")
    print_kv("Repository Type", result.repository_type, bold_value=True)

    if result.repository_type == "s3":
        s3_bucket = result.repository_bucket or "Not configured"

        if result.s3_bucket_exists is True:
            ver_str = (
                "Versioning: Enabled"
                if result.s3_bucket_versioning
                else "Versioning: Disabled"
            )
            enc_str = "Encrypted" if result.s3_bucket_encryption else "Unencrypted"
            bucket_status = f"[green]Available[/green] ({ver_str}, {enc_str})"
        elif result.s3_bucket_exists is False:
            bucket_status = "[red]Bucket Not Found / Missing[/red]"
        elif result.s3_bucket_accessible is False:
            bucket_status = f"[red]Inaccessible[/red] ({result.s3_error or 'Access Denied'})"
        else:
            bucket_status = "[dim]Not Checked[/dim]"

        print_kv("S3 Bucket", f"{s3_bucket} ({bucket_status})")
        print_kv("S3 Object Key", result.repository_object_key)

        if result.s3_object_exists is True:
            size_kb = (result.s3_object_size or 0) / 1024
            mod_str = format_timestamp(result.s3_object_last_modified) or "Unknown"
            etag_str = f"ETag: {result.s3_object_etag}" if result.s3_object_etag else ""
            print_kv(
                "Remote Archive Status",
                f"[green]Present[/green] ({size_kb:.1f} KB, {etag_str}, Last Modified: {mod_str})",
            )
        elif result.s3_object_exists is False:
            print_kv("Remote Archive Status", "Not uploaded yet", style="yellow")

    elif result.repository_type == "codecommit":
        repo_name = result.repository_name or "Not set"
        if result.codecommit_exists is True:
            repo_status = "[green]Available[/green]"
        elif result.codecommit_exists is False:
            repo_status = "[red]Repository Not Found[/red]"
        elif result.codecommit_accessible is False:
            repo_status = f"[red]Inaccessible[/red] ({result.codecommit_error or 'Access Denied'})"
        else:
            repo_status = "[dim]Not Checked[/dim]"

        print_kv("CodeCommit Repository", f"{repo_name} ({repo_status})")
        branch_str = result.repository_branch or "main"
        if result.codecommit_branch_exists is True:
            branch_status = "[green]Exists[/green]"
        elif result.codecommit_branch_exists is False:
            branch_status = "[yellow]Branch Not Found[/yellow]"
        else:
            branch_status = "[dim]Not Checked[/dim]"
        print_kv("Branch", f"{branch_str} ({branch_status})")

    elif result.repository_type == "codeconnection":
        conn_arn = result.codeconnection_arn or "Not set"
        conn_status = format_status(result.codeconnection_status or "Configured")
        print_kv("CodeConnection ARN", f"{conn_arn} ({conn_status})")
        if result.codeconnection_provider:
            print_kv("Provider Type", result.codeconnection_provider)
        print_kv("Repository Owner", result.owner or "Not set")
        print_kv("Repository Name", result.repository_name or "Not set")
        print_kv("Branch", result.repository_branch or "main")

    elif result.repository_type == "git":
        print_kv("Git Repository URL", result.repository_url or result.repository_name or "Not set")
        print_kv("Branch", result.repository_branch or "main")


def _render_pipeline_status(result: ConfigurationStatusResult) -> None:
    console.print()
    print_section(3, "Configuration Pipeline")
    print_kv("Pipeline Name", result.pipeline_name, bold_value=True)

    pipe_status = result.pipeline_status or "Not Executed"
    print_kv("Pipeline Status", format_status(pipe_status))

    if result.pipeline_execution_id:
        print_kv("Latest Execution ID", result.pipeline_execution_id, style="dim")

    if result.pipeline_failed_stage:
        print_kv("Failed Stage", result.pipeline_failed_stage, style="red")
    if result.pipeline_failed_action:
        print_kv("Failed Action", result.pipeline_failed_action, style="red")
    if result.pipeline_error:
        error_lines = [
            line.strip()
            for line in result.pipeline_error.splitlines()
            if line.strip()
        ]
        if len(error_lines) == 1:
            print_kv("Error", error_lines[0], style="red")
        elif error_lines:
            console.print("[red]Error:[/red]")
            for line in error_lines:
                console.print(f"  [red]{line}[/red]")
    if result.pipeline_failed_build_url:
        print_kv("Build Console", result.pipeline_failed_build_url, style="dim")


def _render_state_metadata(result: ConfigurationStatusResult, *, has_state: bool) -> None:
    console.print()
    print_section(4, "Synchronization History")
    if has_state:
        last_push = format_timestamp(result.uploaded_at) or "Never"
        last_pull = format_timestamp(result.downloaded_at) or "Never"
        print_kv("Last Push", last_push)
        print_kv("Last Pull", last_pull)
        if result.recorded_pipeline_execution_id:
            print_kv(
                "Recorded Execution ID",
                result.recorded_pipeline_execution_id,
                style="dim",
            )
    else:
        print_info("No recorded workspace state found.", dim=True)


def _render_warnings(result: ConfigurationStatusResult) -> None:
    if not result.warnings:
        return
    console.print()
    print_section(5, "Diagnostic Warnings & Recommendations")
    for warn in result.warnings:
        print_warning(f"• {warn}")


def render_config_status(result: ConfigurationStatusResult, *, has_state: bool) -> None:
    """Render prepared configuration status without inspecting the workspace."""
    render_workspace_header(
        "LZA Configuration Status",
        customer_name=result.customer_name,
        workspace_dir=result.workspace_dir,
        lza_version=result.lza_version,
        profile=result.profile,
        region=result.region,
        aws_identity=result.aws_identity,
        aws_error=result.aws_error,
    )

    console.print()
    _render_local_config(result)
    _render_repository_settings(result)
    _render_pipeline_status(result)
    _render_state_metadata(result, has_state=has_state)
    _render_warnings(result)


def status_config_command(
    target_dir: Path | None = None,
) -> None:
    """Query workspace configuration metadata and display configuration status."""
    result = get_config_status_workflow(target_dir=target_dir)
    render_config_status(result, has_state=result.has_state)


__all__ = [
    "render_config_status",
    "status_config_command",
]

