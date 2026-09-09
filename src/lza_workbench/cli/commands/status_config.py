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
from lza_workbench.configuration.status import (
    CodeCommitConfigurationRepositoryStatus,
    CodeConnectionConfigurationRepositoryStatus,
    ConfigurationStatusResult,
    GitConfigurationRepositoryStatus,
    S3ConfigurationRepositoryStatus,
)
from lza_workbench.workflows.status_config import (
    get_config_status_workflow,
)


def _render_local_config(result: ConfigurationStatusResult) -> None:
    print_section(1, "Local Configuration")
    workspace = result.workspace
    local_git = result.local_git

    exists_str = "[green]Present[/green]" if workspace.config_dir_exists else "[red]Missing[/red]"
    print_kv("Local Config Path", f"{workspace.config_dir} ({exists_str})")

    if workspace.yaml_files:
        files_preview = ", ".join(workspace.yaml_files[:5])
        suffix = (
            f" ... (+{len(workspace.yaml_files) - 5} more)"
            if len(workspace.yaml_files) > 5
            else ""
        )
        print_kv(
            "YAML Config Files",
            f"{len(workspace.yaml_files)} files ({files_preview}{suffix})",
        )
    else:
        print_kv("YAML Config Files", "0 files found", style="dim")

    if workspace.initialized_at:
        init_str = format_timestamp(workspace.initialized_at) or "Unknown"
        tmpl_str = workspace.template_name or "default"
        print_kv("Configuration Origin", f"Initialized from '{tmpl_str}' template ({init_str})")
    elif workspace.config_dir_exists:
        print_kv("Configuration Origin", "Imported / Unmanaged")

    if local_git.working_tree:
        gwt = local_git.working_tree
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

        if not isinstance(result.repository, S3ConfigurationRepositoryStatus):
            if result.synchronization.remote_sync:
                print_kv(
                    "Remote Sync",
                    format_status(result.synchronization.remote_sync.summary),
                )
            elif local_git.sync_status:
                print_kv("Remote Sync", format_status(local_git.sync_status.summary))



def _render_s3_repository_settings(
    repository: S3ConfigurationRepositoryStatus,
    *,
    result: ConfigurationStatusResult,
) -> None:
    s3_bucket = repository.bucket or "Not configured"
    if repository.bucket_exists is True:
        versioning = "Versioning: Enabled" if repository.bucket_versioning else "Versioning: Disabled"
        encryption = "Encrypted" if repository.bucket_encryption else "Unencrypted"
        bucket_status = f"[green]Available[/green] ({versioning}, {encryption})"
    elif repository.bucket_exists is False:
        bucket_status = "[red]Bucket Not Found / Missing[/red]"
    elif repository.bucket_accessible is False:
        bucket_status = f"[red]Inaccessible[/red] ({repository.error or 'Access Denied'})"
    else:
        bucket_status = "[dim]Not Checked[/dim]"

    print_kv("S3 Bucket", f"{s3_bucket} ({bucket_status})")
    print_kv("S3 Object Key", repository.object_key)
    if repository.object_exists is True:
        size_kb = (repository.object_size or 0) / 1024
        modified = format_timestamp(repository.object_last_modified) or "Unknown"
        etag = f"ETag: {repository.object_etag}" if repository.object_etag else ""
        print_kv(
            "Remote Archive Status",
            f"[green]Present[/green] ({size_kb:.1f} KB, {etag}, Last Modified: {modified})",
        )
    elif repository.object_exists is False:
        print_kv("Remote Archive Status", "Not uploaded yet", style="yellow")

    if result.synchronization.remote_sync:
        print_kv("Remote Sync", format_status(result.synchronization.remote_sync.summary))


def _render_codecommit_repository_settings(
    repository: CodeCommitConfigurationRepositoryStatus,
) -> None:
    repo_name = repository.repository_name or "Not set"
    if repository.exists is True:
        repo_status = "[green]Available[/green]"
    elif repository.exists is False:
        repo_status = "[red]Repository Not Found[/red]"
    elif repository.accessible is False:
        repo_status = f"[red]Inaccessible[/red] ({repository.error or 'Access Denied'})"
    else:
        repo_status = "[dim]Not Checked[/dim]"

    print_kv("CodeCommit Repository", f"{repo_name} ({repo_status})")
    branch = repository.branch_name or "main"
    if repository.branch_exists is True:
        branch_status = "[green]Exists[/green]"
    elif repository.branch_exists is False:
        branch_status = "[yellow]Branch Not Found[/yellow]"
    else:
        branch_status = "[dim]Not Checked[/dim]"
    print_kv("Branch", f"{branch} ({branch_status})")


def _render_codeconnection_repository_settings(
    repository: CodeConnectionConfigurationRepositoryStatus,
) -> None:
    connection_arn = repository.connection_arn or "Not set"
    connection_status = format_status(repository.status or "Configured")
    print_kv("CodeConnection ARN", f"{connection_arn} ({connection_status})")
    if repository.provider:
        print_kv("Provider Type", repository.provider)
    print_kv("Repository Owner", repository.owner or "Not set")
    print_kv("Repository Name", repository.repository_name or "Not set")
    print_kv("Branch", repository.branch_name or "main")


def _render_git_repository_settings(repository: GitConfigurationRepositoryStatus) -> None:
    print_kv(
        "Git Repository URL",
        repository.repository_url or repository.repository_name or "Not set",
    )
    print_kv("Branch", repository.branch_name or "main")


def _render_repository_settings(result: ConfigurationStatusResult) -> None:
    console.print()
    print_section(2, "Repository Settings")
    repository = result.repository
    repository_type = {
        S3ConfigurationRepositoryStatus: "s3",
        CodeCommitConfigurationRepositoryStatus: "codecommit",
        CodeConnectionConfigurationRepositoryStatus: "codeconnection",
        GitConfigurationRepositoryStatus: "git",
    }[type(repository)]
    print_kv("Repository Type", repository_type, bold_value=True)

    if isinstance(repository, S3ConfigurationRepositoryStatus):
        _render_s3_repository_settings(repository, result=result)
    elif isinstance(repository, CodeCommitConfigurationRepositoryStatus):
        _render_codecommit_repository_settings(repository)
    elif isinstance(repository, CodeConnectionConfigurationRepositoryStatus):
        _render_codeconnection_repository_settings(repository)
    elif isinstance(repository, GitConfigurationRepositoryStatus):
        _render_git_repository_settings(repository)


def _render_pipeline_status(result: ConfigurationStatusResult) -> None:
    console.print()
    print_section(3, "Configuration Pipeline")
    pipeline = result.pipeline
    print_kv("Pipeline Name", pipeline.name, bold_value=True)

    pipe_status = pipeline.status or "Not Executed"
    print_kv("Pipeline Status", format_status(pipe_status))

    if pipeline.execution_id:
        print_kv("Latest Execution ID", pipeline.execution_id, style="dim")

    if pipeline.failed_stage:
        print_kv("Failed Stage", pipeline.failed_stage, style="red")
    if pipeline.failed_action:
        print_kv("Failed Action", pipeline.failed_action, style="red")
    if pipeline.error:
        error_lines = [
            line.strip()
            for line in pipeline.error.splitlines()
            if line.strip()
        ]
        if len(error_lines) == 1:
            print_kv("Error", error_lines[0], style="red")
        elif error_lines:
            console.print("[red]Error:[/red]")
            for line in error_lines:
                console.print(f"  [red]{line}[/red]")
    if pipeline.failed_build_url:
        print_kv("Build Console", pipeline.failed_build_url, style="dim")


def _render_state_metadata(result: ConfigurationStatusResult, *, has_state: bool) -> None:
    console.print()
    print_section(4, "Synchronization History")
    synchronization = result.synchronization
    if has_state:
        last_push = format_timestamp(synchronization.uploaded_at) or "Never"
        last_pull = format_timestamp(synchronization.downloaded_at) or "Never"
        print_kv("Last Push", last_push)
        print_kv("Last Pull", last_pull)
        if synchronization.recorded_pipeline_execution_id:
            print_kv(
                "Recorded Execution ID",
                synchronization.recorded_pipeline_execution_id,
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
        customer_name=result.workspace.customer_name,
        workspace_dir=result.workspace.workspace_dir,
        lza_version=result.workspace.lza_version,
        profile=result.workspace.profile,
        region=result.workspace.region,
        aws_identity=result.workspace.aws_identity,
        aws_error=result.workspace.aws_error,
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
    render_config_status(result, has_state=result.synchronization.has_state)



__all__ = [
    "render_config_status",
    "status_config_command",
]
