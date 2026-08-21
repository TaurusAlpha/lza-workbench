"""LZA Workbench command-line interface.

Define the CLI entrypoint and command registrations for workspace management.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from lza_workbench.cli import params
from lza_workbench.cli.commands.config_download import (
    config_download_command as run_cli_download_config,
)
from lza_workbench.cli.commands.config_init import (
    config_init_command as run_cli_init_config,
)
from lza_workbench.cli.commands.config_upload import (
    config_upload_command as run_cli_upload_config,
)
from lza_workbench.cli.commands.installer_deploy import (
    installer_deploy_command as run_cli_installer_deploy,
)
from lza_workbench.cli.commands.installer_plan import (
    installer_init_command as run_cli_installer_init,
)
from lza_workbench.cli.commands.installer_plan import (
    installer_plan_command as run_cli_installer_plan,
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
    dry_run: params.DryRun = False,
    no_save: bool = typer.Option(False, "--no-save", help="Do not save accepted parameters."),
) -> None:
    """Collect and persist installer configuration from the selected template."""
    run_cli_installer_init(
        management_account_email=management_account_email,
        log_archive_account_email=log_archive_account_email,
        audit_account_email=audit_account_email,
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


@installer_app.command("status")
def installer_status_command(
    sync_state: params.SyncState = False,
    sync_config: params.SyncConfig = False,
) -> None:
    """Show the current installer deployment state (alias for `lza status installer`)."""
    run_cli_status_installer(
        sync_state=sync_state,
        sync_config=sync_config,
    )


@status_app.callback(invoke_without_command=True)
def status_root_callback(
    ctx: typer.Context,
) -> None:
    """Show overall workspace status overview."""
    if ctx.invoked_subcommand is None:
        run_cli_status_root()


@status_app.command("installer")
def status_installer_command(
    sync_state: params.SyncState = False,
    sync_config: params.SyncConfig = False,
) -> None:
    """Show the current installer stack status details."""
    run_cli_status_installer(
        sync_state=sync_state,
        sync_config=sync_config,
    )


@status_app.command("config")
def status_config_command() -> None:
    """Show configuration repository status details."""
    run_cli_status_config()


@status_app.command("pipeline")
def status_pipeline_command() -> None:
    """Show CodePipeline status details."""
    run_cli_status_pipeline()


app.add_typer(config_app, name="config")
app.add_typer(installer_app, name="installer")
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
    dry_run: params.DryRun = False,
    force: params.Force = False,
    skip_aws_check: params.SkipAwsCheck = False,
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
        dry_run=dry_run,
        force=force,
        skip_aws_check=skip_aws_check,
        interactive=_is_interactive(),
    )


@app.command("bootstrap")
def bootstrap_command(
    dry_run: params.DryRun = False,
    force: params.Force = False,
) -> None:
    """Create or validate AWS prerequisite resources required by LZA Workbench."""
    run_cli_workspace_bootstrap(
        dry_run=dry_run,
        force=force,
        interactive=_is_interactive(),
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


@config_app.command("upload")
def config_upload_command(
    dry_run: params.DryRun = False,
) -> None:
    """Upload LZA configuration to configured repository destination."""
    run_cli_upload_config(
        dry_run=dry_run,
        interactive=_is_interactive(),
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
