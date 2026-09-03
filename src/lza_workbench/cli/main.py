"""LZA Workbench command-line interface.

Define the CLI entrypoint and command registrations for workspace management.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from lza_workbench.cli import params
from lza_workbench.cli.commands.config_deploy import (
    config_deploy_command as run_cli_deploy_config,
)
from lza_workbench.cli.commands.config_download import (
    config_download_command as run_cli_download_config,
)
from lza_workbench.cli.commands.config_init import (
    config_init_command as run_cli_init_config,
)
from lza_workbench.cli.commands.config_pull import (
    config_pull_command as run_cli_pull_config,
)
from lza_workbench.cli.commands.config_push import (
    config_push_command as run_cli_push_config,
)
from lza_workbench.cli.commands.config_upload import (
    config_upload_command as run_cli_upload_config,
)
from lza_workbench.cli.commands.installer_deploy import (
    installer_deploy_command as run_cli_installer_deploy,
)
from lza_workbench.cli.commands.installer_import import (
    installer_import_command as run_cli_installer_import,
)
from lza_workbench.cli.commands.installer_init import (
    installer_init_command as run_cli_installer_init,
)
from lza_workbench.cli.commands.installer_plan import (
    installer_plan_command as run_cli_installer_plan,
)
from lza_workbench.cli.commands.pipeline_start import (
    pipeline_start_command as run_cli_pipeline_start,
)
from lza_workbench.cli.commands.pipeline_watch import (
    pipeline_watch_command as run_cli_pipeline_watch,
)
from lza_workbench.cli.commands.status_config import (
    status_config_command as run_cli_status_config,
)
from lza_workbench.cli.commands.status_installer import (
    status_installer_command as run_cli_status_installer,
)
from lza_workbench.cli.commands.status_pipeline import (
    status_pipeline_command as run_cli_status_pipeline,
)
from lza_workbench.cli.commands.status_root import (
    status_root_command as run_cli_status_root,
)
from lza_workbench.cli.commands.workspace_bootstrap import (
    workspace_bootstrap_command as run_cli_workspace_bootstrap,
)
from lza_workbench.cli.commands.workspace_import import (
    workspace_import_command as run_cli_workspace_import,
)
from lza_workbench.cli.commands.workspace_init import (
    workspace_init_command as run_cli_workspace_init,
)
from lza_workbench.cli.output import print_error
from lza_workbench.errors import LzaError

app = typer.Typer(
    help="LZA Workbench CLI",
    no_args_is_help=True,
    add_completion=False,
)

config_app = typer.Typer(
    help="Manage LZA configuration.",
    no_args_is_help=True,
)

installer_app = typer.Typer(
    help="Manage LZA installer stack.",
    no_args_is_help=True,
)

pipeline_app = typer.Typer(
    help="Manage LZA pipeline executions.",
    no_args_is_help=True,
)

status_app = typer.Typer(
    help="Show status of workspace components.",
    no_args_is_help=False,
    invoke_without_command=True,
)


@installer_app.command("init")
def installer_init_command(
    management_account_email: params.ManagementAccountEmail = None,
    log_archive_account_email: params.LogArchiveAccountEmail = None,
    audit_account_email: params.AuditAccountEmail = None,
    accelerator_prefix: params.AcceleratorPrefix = None,
    dry_run: params.DryRun = False,
    no_save: bool = typer.Option(False, "--no-save", help="Do not save accepted parameters."),
) -> None:
    """Collect and persist installer configuration from the selected template."""
    run_cli_installer_init(
        management_account_email=management_account_email,
        log_archive_account_email=log_archive_account_email,
        audit_account_email=audit_account_email,
        accelerator_prefix=accelerator_prefix,
        dry_run=dry_run,
        no_save=no_save,
        interactive=_is_interactive(),
    )


@installer_app.command("plan")
def installer_plan_command(
    dry_run: params.DryRun = False,
) -> None:
    """Show the AWS actions required to deploy initialized installer configuration."""
    run_cli_installer_plan(dry_run=dry_run)


@installer_app.command("deploy")
def installer_deploy_command(
    dry_run: params.DryRun = False,
    force: params.Force = False,
) -> None:
    """Deploy the LZA installer CloudFormation stack for the current workspace."""
    run_cli_installer_deploy(
        dry_run=dry_run,
        force=force,
    )


@installer_app.command("import")
def installer_import_command(
    installer_stack_name: params.InstallerStackName = None,
    dry_run: params.DryRun = False,
) -> None:
    """Import deployed CloudFormation installer parameters (alias for `lza import installer`)."""
    run_cli_installer_import(
        installer_stack_name=installer_stack_name,
        dry_run=dry_run,
    )


@installer_app.command("status")
def installer_status_command() -> None:
    """Show the current installer deployment state (alias for `lza status installer`)."""
    run_cli_status_installer()


@status_app.callback(invoke_without_command=True)
def status_root_callback(
    ctx: typer.Context,
) -> None:
    """Show overall workspace status overview."""
    if ctx.invoked_subcommand is None:
        run_cli_status_root()


@status_app.command("installer")
def status_installer_command() -> None:
    """Show the current installer stack status details."""
    run_cli_status_installer()


@config_app.command("status")
def config_status_command() -> None:
    """Show configuration repository status details."""
    run_cli_status_config()


@status_app.command("config")
def status_config_command() -> None:
    """Show configuration repository status details."""
    run_cli_status_config()


@status_app.command("pipeline")
def status_pipeline_command() -> None:
    """Show CodePipeline status details."""
    run_cli_status_pipeline()


@pipeline_app.command("start")
def pipeline_start_command(
    pipeline_name: params.PipelineName = None,
    dry_run: params.DryRun = False,
    allow_concurrent: params.AllowConcurrent = False,
) -> None:
    """Start an LZA CodePipeline execution."""
    run_cli_pipeline_start(
        pipeline_name=pipeline_name,
        dry_run=dry_run,
        allow_concurrent=allow_concurrent,
    )


@pipeline_app.command("watch")
def pipeline_watch_command(
    pipeline_name: params.PipelineName = None,
    execution_id: params.ExecutionId = None,
    poll_interval: params.PollInterval = None,
    verbose: params.Verbose = False,
) -> None:
    """Monitor an existing LZA CodePipeline execution."""
    run_cli_pipeline_watch(
        pipeline_name=pipeline_name,
        execution_id=execution_id,
        poll_interval=poll_interval,
        verbose=verbose,
    )


app.add_typer(config_app, name="config")
app.add_typer(installer_app, name="installer")
app.add_typer(pipeline_app, name="pipeline")
app.add_typer(status_app, name="status")


def _is_interactive() -> bool:
    return sys.stdin.isatty()


@app.callback()
def root(version: params.Version = False) -> None:
    """Run LZA Workbench."""


@app.command("init")
def init_command(
    customer_name: params.CustomerName,
    workspace_dir: params.WorkspaceDir = None,
    aws_auth_type: params.AwsAuthType = "profile",
    aws_profile: params.AwsProfile = "",
    aws_region: params.AwsRegion = "",
    lza_version: params.LzaVersion = None,
    dry_run: params.DryRun = False,
    force: params.Force = False,
    skip_aws_check: params.SkipAwsCheck = True,
) -> None:
    """Create a new customer-specific LZA workspace."""

    run_cli_workspace_init(
        customer_name=customer_name,
        workspace_dir=workspace_dir,
        aws_auth_type=aws_auth_type,
        aws_profile=aws_profile,
        aws_region=aws_region,
        lza_version=lza_version,
        dry_run=dry_run,
        force=force,
        skip_aws_check=skip_aws_check,
        interactive=_is_interactive(),
    )


@app.command("import")
def import_command(
    workspace_dir: params.ImportWorkspaceDir = Path("."),
    customer_name: params.ImportCustomerName = None,
    config_dir: params.LzaConfigDir = None,
    aws_auth_type: params.AwsAuthType = "profile",
    aws_profile: params.AwsProfile = "",
    aws_region: params.AwsRegion = "",
    lza_version: params.LzaVersion = None,
    installer_stack_name: params.InstallerStackName = None,
    dry_run: params.DryRun = False,
    force: params.Force = False,
    repair: params.Repair = False,
    skip_aws_check: params.SkipAwsCheck = False,
    prime_credentials: params.PrimeCredentials = False,
) -> None:
    """Adopt an existing customer-owned LZA configuration."""
    run_cli_workspace_import(
        customer_name=customer_name,
        workspace_dir=workspace_dir,
        config_dir=config_dir,
        aws_auth_type=aws_auth_type,
        aws_profile=aws_profile,
        aws_region=aws_region,
        lza_version=lza_version,
        installer_stack_name=installer_stack_name,
        dry_run=dry_run,
        force=force,
        repair=repair,
        skip_aws_check=skip_aws_check,
        prime_credentials=prime_credentials,
        interactive=_is_interactive(),
    )


@app.command("bootstrap")
def bootstrap_command(
    dry_run: params.DryRun = False,
    force: params.Force = False,
    github_token: params.GithubToken = None,
    allow_missing_github_secret: params.AllowMissingGithubSecret = False,
) -> None:
    """Create or validate AWS prerequisite resources required by LZA Workbench."""
    run_cli_workspace_bootstrap(
        dry_run=dry_run,
        force=force,
        interactive=_is_interactive(),
        github_token=github_token,
        allow_missing_github_secret=allow_missing_github_secret,
    )


@config_app.command("init")
def config_init_command(
    template: params.ConfigTemplate = None,
    force: params.Force = False,
    dry_run: params.DryRun = False,
) -> None:
    """Initialize local LZA configuration in the current workspace from a template."""
    run_cli_init_config(
        template=template,
        force=force,
        dry_run=dry_run,
    )


@config_app.command("download")
def config_download_command(
    dry_run: params.DryRun = False,
    force: params.Force = False,
    extract: params.Extract = True,
) -> None:
    """Download LZA configuration from configured repository source."""
    run_cli_download_config(
        dry_run=dry_run,
        force=force,
        extract=extract,
        interactive=_is_interactive(),
    )


@config_app.command("pull")
def config_pull_command(
    dry_run: params.DryRun = False,
    force: params.Force = False,
    extract: params.Extract = True,
) -> None:
    """Synchronize remote LZA configuration to local workspace."""
    run_cli_pull_config(
        dry_run=dry_run,
        force=force,
        extract=extract,
        interactive=_is_interactive(),
    )


@config_app.command("push")
def config_push_command(
    dry_run: params.DryRun = False,
) -> None:
    """Synchronize local LZA configuration to configured remote repository."""
    run_cli_push_config(
        dry_run=dry_run,
        interactive=_is_interactive(),
    )


@config_app.command("upload")
def config_upload_command(
    dry_run: params.DryRun = False,
) -> None:
    """Upload LZA configuration to configured repository destination (alias for push)."""
    run_cli_upload_config(
        dry_run=dry_run,
        interactive=_is_interactive(),
    )


@config_app.command("deploy")
def config_deploy_command(
    dry_run: params.DryRun = False,
    no_watch: params.NoWatch = False,
    verbose: params.Verbose = False,
) -> None:
    """Synchronize configuration to remote destination and trigger LZA pipeline execution."""
    run_cli_deploy_config(
        dry_run=dry_run,
        no_watch=no_watch,
        verbose=verbose,
    )


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a process-style exit code."""
    try:
        app(args=argv, standalone_mode=False)
    except typer.Exit as exc:
        return int(exc.exit_code or 0)
    except LzaError as exc:
        print_error(str(exc))
        return 1
    except Exception as exc:
        show = getattr(exc, "show", None)
        exit_code = getattr(exc, "exit_code", None)
        if callable(show) and isinstance(exit_code, int):
            show()
            if exc.__class__.__name__ == "NoArgsIsHelpError":
                return 0
            return exit_code
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
