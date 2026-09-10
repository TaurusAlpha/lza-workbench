"""CLI commands and presentation for configuration lifecycle."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import typer

from lza_workbench.configuration.application.deploy import (
    ConfigDeployError,
    ConfigDeployResult,
    deploy_configuration_workflow,
)
from lza_workbench.configuration.application.initialize import (
    ConfigInitResult,
    init_config_workflow,
)
from lza_workbench.configuration.application.pull import (
    ConfigPullRequest,
    ConfigPullResult,
    apply_config_pull,
    prepare_config_pull,
)
from lza_workbench.configuration.application.push import (
    ConfigPushRequest,
    ConfigPushResult,
    apply_config_push,
    prepare_config_push,
)
from lza_workbench.configuration.templates import (
    DEFAULT_TEMPLATE_SOURCE,
    list_packaged_templates,
)
from lza_workbench.interfaces.cli import params
from lza_workbench.interfaces.cli.input import value_or_prompt
from lza_workbench.interfaces.cli.output import (
    console,
    print_diff_summary,
    print_dry_run_header,
    print_info,
    print_kv,
    print_section,
    print_success,
    print_warning,
)
from lza_workbench.interfaces.cli.pipeline import (
    PipelineWatchMonitor,
    render_pipeline_start_result,
    render_pipeline_watch_result,
)


def render_config_init_result(result: ConfigInitResult) -> None:
    """Render the results of configuration initialization."""
    workspace_dir = result.workspace_dir
    config_dir = result.config_dir
    template_name = result.template_source.source

    if result.skipped:
        if result.is_managed:
            init_str = (
                result.initialized_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                if result.initialized_at
                else "previously"
            )
            print_info(
                f"Configuration directory '{config_dir}' already exists "
                f"(initialized from template '{template_name}' on {init_str})."
            )
            if result.drifted_fields:
                drifted_str = ", ".join(result.drifted_fields)
                print_warning(
                    f"Workspace settings changed since initialization ({drifted_str}). "
                    "Run 'lza config init --force' to re-apply the template with "
                    "current workspace settings."
                )
            else:
                print_info(
                    "Use 'lza config init --force' to re-initialize or overwrite.",
                    dim=True,
                )
        else:
            print_warning(
                f"Configuration directory '{config_dir}' already exists "
                "(unmanaged or manually created). "
                f"Use 'lza config init --force' to overwrite with template '{template_name}'."
            )
        return

    if result.dry_run:
        print_dry_run_header("lza config init")
        print_kv("Workspace", workspace_dir)
        print_kv("Template", template_name)
        print_kv("Config target", config_dir)
        console.print("Planned writes:")
        for path in result.written_paths:
            console.print(f"  - {path}")
        if result.unresolved_placeholders:
            print_warning(f"Unresolved placeholders ({len(result.unresolved_placeholders)}):")
            for token in result.unresolved_placeholders:
                console.print(f"  - {token}")
        if result.config.configuration.repository.type == "s3" and not result.git_skipped:
            console.print("Planned Git initialization:")
            console.print("  - Initialize local Git repository")
            console.print("  - Create initial commit")
        elif result.git_skipped and result.git_skip_reason:
            print_info(f"Git repository: Skipped ({result.git_skip_reason})", dim=True)
        return

    print_success("Initialized LZA configuration")
    print_kv("Workspace", workspace_dir)
    print_kv("Template", template_name)
    print_kv("Config target", config_dir)
    print_kv("Files written", len(result.written_paths))
    if result.git_initialized and result.git_committed:
        print_kv("Git repository", "Initialized with initial commit")
    elif result.git_skipped and result.git_skip_reason:
        print_kv("Git repository", f"Skipped ({result.git_skip_reason})", style="dim")

    if result.unresolved_placeholders:
        console.print()
        print_warning(f"Unresolved placeholders remaining ({len(result.unresolved_placeholders)}):")
        for token in result.unresolved_placeholders:
            console.print(f"  - {token}")
        print_info(
            "Run 'lza installer init' to configure account emails, "
            "then 'lza config init --force' to resolve them.",
            dim=True,
        )


def config_init_command(
    *,
    template: params.ConfigTemplate = None,
    force: params.Force = False,
    dry_run: params.DryRun = False,
) -> None:
    """Initialize local LZA configuration in the current workspace from a packaged template."""
    resolved_template = template
    if resolved_template is None:
        packaged = list_packaged_templates()
        if len(packaged) == 1:
            resolved_template = packaged[0]
        elif len(packaged) > 1:
            default_template = (
                DEFAULT_TEMPLATE_SOURCE if DEFAULT_TEMPLATE_SOURCE in packaged else packaged[0]
            )
            console.print("Available configuration templates:")
            for idx, name in enumerate(packaged, start=1):
                console.print(f"  {idx}. {name}")

            def _validate_choice(val: str) -> str:
                val = val.strip()
                if val in packaged:
                    return val
                if val.isdigit():
                    idx = int(val)
                    if 1 <= idx <= len(packaged):
                        return packaged[idx - 1]
                raise ValueError(
                    f"Invalid template choice '{val}'. Choose from: {', '.join(packaged)}"
                )

            resolved_template = value_or_prompt(
                "Select configuration template",
                value=None,
                default=default_template,
                interactive=True,
                validator=_validate_choice,
            )

    result = init_config_workflow(
        target_dir=Path.cwd(),
        template_name=resolved_template,
        force=force,
        dry_run=dry_run,
    )
    render_config_init_result(result)


def render_config_push_result(result: ConfigPushResult) -> None:
    """Render the results of a configuration push workflow."""
    if result.dry_run:
        print_dry_run_header("lza config push")
        if result.safety_warning:
            print_warning(result.safety_warning)
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
    force: params.ConfigPushForce = False,
    interactive: bool = False,
    target_dir: Path | None = None,
) -> ConfigPushResult:
    """Synchronize LZA configuration to configured repository destination."""
    request = ConfigPushRequest(
        target_dir=target_dir,
        dry_run=dry_run,
        force=force,
    )
    preparation = prepare_config_push(request)
    if preparation.confirmation_message and interactive and not dry_run:
        if typer.confirm(f"{preparation.confirmation_message} Continue?", default=False):
            request = replace(request, overwrite_confirmed=True)
    result = apply_config_push(request)
    render_config_push_result(result)
    return result


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
        if result.restored_changes:
            print_kv("Local Changes", "Uncommitted changes were restored")
        elif result.stashed_changes:
            print_kv("Local Changes", "Uncommitted changes were stashed")


def config_pull_command(
    dry_run: params.DryRun = False,
    force: params.Force = False,
    extract: params.Extract = True,
    interactive: bool = False,
    target_dir: Path | None = None,
) -> ConfigPullResult:
    """Synchronize LZA configuration from configured remote repository or S3."""
    request = ConfigPullRequest(
        target_dir=target_dir,
        dry_run=dry_run,
        force=force,
        extract=extract,
    )
    preparation = prepare_config_pull(request)
    if preparation.confirmation_message and interactive and not dry_run:
        if typer.confirm(preparation.confirmation_message, default=False):
            request = replace(request, overwrite_confirmed=True)
    result = apply_config_pull(request)
    render_config_pull_result(result)
    return result


def render_config_deploy_result(
    result: ConfigDeployResult,
    *,
    verbose: bool = False,
) -> None:
    """Render the full results of configuration deployment."""
    if result.dry_run:
        print_dry_run_header("lza config deploy")
        console.print("[bold]Step 1: Configuration Push (Planned)[/bold]")
        if result.push_result:
            render_config_push_result(result.push_result)
        console.print()
        console.print("[bold]Step 2: Pipeline Execution (Planned)[/bold]")
        if result.start_result:
            render_pipeline_start_result(result.start_result)
        return

    print_section(1, "Configuration Synchronization")
    if result.push_result:
        render_config_push_result(result.push_result)

    console.print()
    print_section(2, "Pipeline Execution Trigger")
    if result.start_result:
        render_pipeline_start_result(result.start_result)

    if result.watch_result is not None:
        render_pipeline_watch_result(
            result.watch_result,
            verbose=verbose,
            start_section_number=3,
        )


def config_deploy_command(
    dry_run: params.DryRun = False,
    no_watch: params.NoWatch = False,
    verbose: params.Verbose = False,
    target_dir: Path | None = None,
) -> ConfigDeployResult:
    """Synchronize configuration to remote destination and trigger LZA pipeline execution."""
    monitor = PipelineWatchMonitor()
    try:
        result = deploy_configuration_workflow(
            target_dir=target_dir,
            dry_run=dry_run,
            watch=not no_watch,
            on_watch_update=monitor.update,
        )
    except ConfigDeployError as exc:
        render_config_deploy_result(exc.result, verbose=verbose)
        raise
    finally:
        monitor.stop()

    render_config_deploy_result(result, verbose=verbose)

    return result


__all__ = [
    "config_deploy_command",
    "render_config_deploy_result",
]
