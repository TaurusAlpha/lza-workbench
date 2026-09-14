"""CLI commands and presentation for workspace status views."""

from __future__ import annotations

from pathlib import Path

from rich.table import Table

from lza_workbench.configuration.status import (
    CodeCommitConfigurationRepositoryStatus,
    CodeConnectionConfigurationRepositoryStatus,
    ConfigurationStatusResult,
    GitConfigurationRepositoryStatus,
    S3ConfigurationRepositoryStatus,
    get_config_status_workflow,
)
from lza_workbench.installer.status import (
    InstallerStatusResult,
    get_installer_status_workflow,
    normalize_lza_version,
)
from lza_workbench.interfaces.cli.output import (
    console,
    format_duration,
    format_status,
    format_timestamp,
    print_info,
    print_kv,
    print_notice,
    print_section,
    print_warning,
    render_workspace_header,
)
from lza_workbench.status.observer import (
    PipelineSummary,
    RootStatusResult,
    get_root_status_workflow,
)


def _render_recorded_pipeline_summary(pipe: PipelineSummary) -> None:
    if pipe.status:
        print_kv("Latest Execution", f"{format_status(pipe.status)} (Recorded)")
    else:
        print_kv("Latest Execution", "None Recorded", style="dim")
    if pipe.execution_id:
        print_kv("Execution ID", f"{pipe.execution_id} (Recorded)", style="dim")
    if pipe.failed_stage:
        print_kv("Failed Stage", f"{pipe.failed_stage} (Recorded)", style="red")
    if pipe.failed_action:
        print_kv("Failed Action", f"{pipe.failed_action} (Recorded)", style="red")
    if pipe.failure_summary:
        print_kv("Failure", pipe.failure_summary, style="red")


def _render_live_pipeline_details(pipe: PipelineSummary) -> None:
    if pipe.start_time:
        print_kv("Started", format_timestamp(pipe.start_time))
    if pipe.duration_seconds is not None:
        duration = format_duration(pipe.duration_seconds)
        if duration:
            print_kv("Duration", duration)
    if pipe.current_stage or pipe.current_action:
        stage_action = " / ".join(filter(None, [pipe.current_stage, pipe.current_action]))
        print_kv("Current Stage/Action", stage_action, style="yellow")
    if pipe.failed_stage:
        print_kv("Failed Stage", pipe.failed_stage, style="red")
    if pipe.failed_action:
        print_kv("Failed Action", pipe.failed_action, style="red")
    if pipe.failure_summary:
        print_kv("Failure", pipe.failure_summary, style="red")


def _render_pipeline_summary(
    pipe: PipelineSummary,
    *,
    label_prefix: str,
) -> None:
    print_kv(f"{label_prefix} Pipeline", pipe.name, bold_value=True)
    if not pipe.is_live:
        _render_recorded_pipeline_summary(pipe)
        return

    if not pipe.exists:
        print_kv("Latest Execution", "[dim]Not Deployed[/dim]")
        return

    print_kv("Latest Execution", format_status(pipe.status or "Unknown"))
    if pipe.execution_id:
        print_kv("Execution ID", pipe.execution_id, style="dim")
    _render_live_pipeline_details(pipe)


def render_root_status(result: RootStatusResult) -> None:
    """Render a root status result without querying AWS or the filesystem."""
    render_workspace_header(
        "LZA Workspace Summary",
        customer_name=result.customer_name,
        workspace_dir=result.workspace_dir,
        lza_version=result.lza_version,
        profile=result.profile,
        region=result.region,
        aws_identity=result.aws_identity,
        aws_error=result.aws_error,
    )

    # 1. Installer Summary
    console.print()
    print_section(1, "Installer")
    inst_stack = result.installer
    print_kv("Stack Name", inst_stack.name, bold_value=True)
    if inst_stack.is_live:
        if inst_stack.exists:
            print_kv("Stack Status", format_status(inst_stack.status))
            if inst_stack.deployed_version:
                print_kv("Deployed Version", inst_stack.deployed_version, bold_value=True)
        else:
            print_info("Stack Status: Not Deployed / Not Found", dim=True)
    else:
        if inst_stack.status:
            print_kv("Stack Status", f"{format_status(inst_stack.status)} (Recorded)")
        else:
            print_kv("Stack Status", "Not Recorded", style="dim")
        if inst_stack.deployed_version:
            print_kv("Deployed Version", f"{inst_stack.deployed_version} (Recorded)")
        else:
            print_kv("Deployed Version", "Not Recorded", style="dim")

    console.print()
    _render_pipeline_summary(result.installer_pipeline, label_prefix="Installer")

    # 2. Configuration Summary
    console.print()
    print_section(2, "Configuration")
    crepo = result.configuration_repo
    target_str = f"{crepo.repository_type} / {crepo.target or 'Not configured'}"
    print_kv("Repository", target_str, bold_value=True)

    if crepo.local_git_branch:
        tree_state = (
            "[green]Clean[/green]"
            if crepo.local_git_clean
            else f"[yellow]Dirty ({crepo.local_git_uncommitted} uncommitted)[/yellow]"
        )
        print_kv("Local Git", f"{crepo.local_git_branch} ({tree_state})")
    else:
        print_kv("Local Git", "Not a git repository", style="dim")

    if crepo.remote_sync:
        print_kv("Remote Sync", format_status(crepo.remote_sync.summary))
    elif crepo.git_sync_status:
        print_kv("Remote Sync", format_status(crepo.git_sync_status.summary))
    elif crepo.is_live:
        print_kv("Remote Sync", format_status("Not Git"))
    else:
        print_kv("Remote Sync", format_status("Not Checked (AWS Unavailable)"))

    console.print()
    _render_pipeline_summary(result.configuration_pipeline, label_prefix="Configuration")

    # 3. Overall Status Summary
    console.print()
    print_section(3, "Overall Status")
    health = result.health
    print_kv("Installer", format_status(health.installer))
    print_kv("Configuration", format_status(health.configuration))
    print_kv("Workspace", format_status(health.workspace), bold_value=True)

    console.print()
    console.print("[bold cyan]Subcommands available for filtered status details:[/bold cyan]")
    console.print(
        "  [bold green]lza status installer[/bold green]  "
        "[dim](Detailed stack & pipeline status, drift & sync)[/dim]"
    )
    console.print(
        "  [bold green]lza status config[/bold green]     "
        "[dim](Detailed configuration repo status & sync)[/dim]"
    )


def status_root_command(
    target_dir: Path | None = None,
) -> None:
    """Display overall summary status for the customer LZA workspace."""
    result = get_root_status_workflow(target_dir=target_dir)
    render_root_status(result)


__all__ = [
    "render_root_status",
    "status_root_command",
]

def _render_resources(result: InstallerStatusResult) -> None:
    console.print()
    print_section(1, "Installer Stack")
    status = result.cfn_status.stack_status or "UNKNOWN"
    stack_name = result.config.installer.stack_name or "AWSAccelerator-InstallerStack"

    print_kv("Target Region", result.region, bold_value=True)
    print_kv("Installer Stack Name", stack_name, bold_value=True)
    print_kv("Stack Status", format_status(status))
    print_kv("Installer Pipeline Name", result.installer_pipeline_name, bold_value=True)

    if result.pipeline_state:
        pipe_status = result.pipeline_state.status or "UNKNOWN"
        print_kv("Pipeline Status", format_status(pipe_status))
        if result.pipeline_state.latest_execution_id:
            print_kv(
                "Latest Execution ID",
                result.pipeline_state.latest_execution_id,
                style="dim",
            )
        if result.pipeline_state.stages:
            stage_parts = []
            for s in result.pipeline_state.stages:
                s_status = s.status or "Unknown"
                stage_parts.append(f"{s.stage_name} ({format_status(s_status)})")
            print_kv("Pipeline Stages", " -> ".join(stage_parts))
        if result.pipeline_state.error:
            print_notice(f"Pipeline Query Notice: {result.pipeline_state.error}")

    created = format_timestamp(result.cfn_status.creation_time)
    if created:
        print_kv("Stack Creation Time", created)
    updated = format_timestamp(result.cfn_status.last_updated_time)
    if updated:
        print_kv("Stack Last Updated", updated)
    if result.cfn_status.error:
        print_notice(f"CloudFormation Query Notice: {result.cfn_status.error}")


def _render_deployed_details(result: InstallerStatusResult) -> None:
    console.print()
    print_section(2, "Deployed Installer Details")
    params_data = result.cfn_status.deployed_parameters
    if not result.cfn_status.exists or not params_data:
        _render_installer_source_details(result, {})
        print_info("Deployed details unavailable (stack not deployed or unreadable).", dim=True)
        return
    print_kv("Deployed LZA Version", result.deployed_version, bold_value=True)
    _render_installer_source_details(result, params_data)
    matches = normalize_lza_version(result.config.lza.version) == normalize_lza_version(
        result.deployed_version
    )
    print_kv(
        "Version Match",
        "Match (Configured matches Deployed)"
        if matches
        else (
            f"Mismatch (Configured: {result.config.lza.version}, "
            f"Deployed: {result.deployed_version})"
        ),
        style="green" if matches else "yellow",
    )


def _render_installer_source_details(
    result: InstallerStatusResult, parameters: dict[str, str]
) -> None:
    """Render only the source fields that apply to the active installer source."""
    source_config = result.config.installer.source_code
    source_type = parameters.get("RepositorySource", source_config.repository_type).lower()
    print_kv(
        "Source Type",
        source_type,
        bold_value=True,
    )
    if source_type == "s3":
        print_kv("Bucket", parameters.get("RepositoryBucketName", source_config.bucket or "N/A"))
        print_kv("Object Key", parameters.get("RepositoryBucketObject", source_config.key or "N/A"))
    elif source_type == "github":
        owner = parameters.get("RepositoryOwner", source_config.owner or "N/A")
        repository_name = parameters.get("RepositoryName", source_config.repository_name or "N/A")
        print_kv("Repository", f"{owner}/{repository_name}")
        print_kv("Branch", parameters.get("RepositoryBranchName", source_config.branch or "N/A"))
    elif source_type == "codecommit":
        print_kv(
            "Repository",
            parameters.get("RepositoryName", source_config.repository_name or "N/A"),
        )
        print_kv("Branch", parameters.get("RepositoryBranchName", source_config.branch or "N/A"))
    elif source_type == "codeconnection":
        connection_arn = (
            parameters.get("RepositoryCodeConnectionArn")
            or parameters.get("CodeConnectionArn")
            or source_config.connection_arn
            or "N/A"
        )
        print_kv("Connection ARN", connection_arn)


def _render_drift(result: InstallerStatusResult) -> None:
    console.print()
    print_section(3, "Configuration Drift")
    if not result.cfn_status.exists or not result.cfn_status.deployed_parameters:
        print_info("Drift check skipped (stack is not deployed).", dim=True)
        return
    if not result.configuration_drift:
        print_info("No configuration drift detected.", style="green")
        return
    table = Table(title="Detected Parameter Drift", show_header=True)
    table.add_column("Parameter Key", style="cyan")
    table.add_column("Deployed Value", style="red")
    table.add_column("Configured Value", style="green")
    for key, (deployed, configured) in sorted(result.configuration_drift.items()):
        table.add_row(key, deployed, configured)
    console.print(table)


def _render_state_alignment(result: InstallerStatusResult) -> None:
    console.print()
    print_section(4, "State Alignment")
    if not result.state:
        print_info("No recorded workspace state found.", dim=True)
        return
    state = result.state
    rec_status = (
        format_status(state.installer.stack_status) if state.installer.stack_status else None
    )
    for label, value in (
        ("Recorded Stack ID", state.installer.stack_id),
        ("Recorded Stack Status", rec_status),
        ("Recorded Stack Updated", format_timestamp(state.installer.stack_updated_at)),
        ("Installer Downloaded", format_timestamp(state.installer.downloaded_at)),
        ("Template Version", state.installer.template_version),
    ):
        if value:
            print_kv(label, value)
    if result.state_alignment:
        print_kv(
            "State Alignment",
            "In Sync (Recorded state matches live AWS deployment)"
            if result.state_alignment.in_sync
            else "Out of Sync",
            style="green" if result.state_alignment.in_sync else "yellow",
        )


def _render_recommendations(result: InstallerStatusResult) -> None:
    state_out_of_sync = result.state_alignment is not None and not result.state_alignment.in_sync
    if not result.cfn_status.exists or (not result.configuration_drift and not state_out_of_sync):
        return
    console.print()
    console.print("[bold cyan]Recommended Next Command:[/bold cyan]")
    if result.configuration_drift or state_out_of_sync:
        console.print(
            "  [bold green]lza installer import[/bold green]  "
            "[dim](Synchronizes lza-workspace.yaml and recorded state "
            "with live AWS settings)[/dim]"
        )
        console.print(
            "  [bold green]lza installer deploy[/bold green]  "
            "[dim](Reconcile deployed installer stack with local configuration values)[/dim]"
        )


def render_installer_status(result: InstallerStatusResult) -> None:
    """Render prepared installer data without AWS calls or workspace writes."""
    render_workspace_header(
        "LZA Installer Status",
        customer_name=result.config.customer.name,
        workspace_dir=result.workspace_dir,
        lza_version=result.config.lza.version,
        profile=result.profile,
        region=result.region,
        aws_identity=result.aws_identity,
        aws_error=result.aws_error,
    )
    _render_resources(result)
    _render_deployed_details(result)
    _render_drift(result)
    _render_state_alignment(result)
    _render_recommendations(result)


def status_installer_command(
    target_dir: Path | None = None,
) -> None:
    """Query AWS and render an installer status report."""
    result = get_installer_status_workflow(
        target_dir=target_dir,
    )
    render_installer_status(result)


__all__ = [
    "render_installer_status",
    "status_installer_command",
]

def _render_local_config(result: ConfigurationStatusResult) -> None:
    print_section(1, "Local Configuration")
    workspace = result.workspace
    local_git = result.local_git

    exists_str = "[green]Present[/green]" if workspace.config_dir_exists else "[red]Missing[/red]"
    print_kv("Local Config Path", f"{workspace.config_dir} ({exists_str})")

    if workspace.yaml_files:
        files_preview = ", ".join(workspace.yaml_files[:5])
        suffix = (
            f" ... (+{len(workspace.yaml_files) - 5} more)" if len(workspace.yaml_files) > 5 else ""
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
        versioning = (
            "Versioning: Enabled" if repository.bucket_versioning else "Versioning: Disabled"
        )
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
        error_lines = [line.strip() for line in pipeline.error.splitlines() if line.strip()]
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
