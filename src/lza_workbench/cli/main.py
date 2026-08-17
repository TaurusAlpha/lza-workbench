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
from lza_workbench.cli.commands.config_upload import (
    config_upload_command as run_cli_upload_config,
)
from lza_workbench.cli.presentation import print_error
from lza_workbench.commands.installer_deploy import run_installer_deploy
from lza_workbench.commands.installer_plan import run_installer_plan
from lza_workbench.commands.status.config import run_config_status
from lza_workbench.commands.status.installer import run_installer_status
from lza_workbench.commands.status.main import run_root_status
from lza_workbench.commands.status.pipeline import run_pipeline_status
from lza_workbench.commands.workspace_import import run_import
from lza_workbench.commands.workspace_init import run_init
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


@installer_app.command("plan")
def installer_plan_command(
    dry_run: params.DryRun = False,
    no_save: bool = False,
) -> None:
    """Resolve and persist installer configuration, then show the actions required to deploy."""
    run_installer_plan(
        dry_run=dry_run,
        no_save=no_save,
    )


@installer_app.command("deploy")
def installer_deploy_command(
    dry_run: params.DryRun = False,
    force: params.Force = False,
) -> None:
    """Deploy the LZA installer CloudFormation stack for the current workspace."""
    run_installer_deploy(
        dry_run=dry_run,
        force=force,
    )


@installer_app.command("status")
def installer_status_command(
    sync_state: params.SyncState = False,
    sync_config: params.SyncConfig = False,
) -> None:
    """Show the current installer deployment state (alias for `lza status installer`)."""
    run_installer_status(
        sync_state=sync_state,
        sync_config=sync_config,
    )


@status_app.callback(invoke_without_command=True)
def status_root_callback(
    ctx: typer.Context,
) -> None:
    """Show overall workspace status overview."""
    if ctx.invoked_subcommand is None:
        run_root_status()


@status_app.command("installer")
def status_installer_command(
    sync_state: params.SyncState = False,
    sync_config: params.SyncConfig = False,
) -> None:
    """Show the current installer stack status details."""
    run_installer_status(
        sync_state=sync_state,
        sync_config=sync_config,
    )


@status_app.command("config")
def status_config_command() -> None:
    """Show configuration repository status details."""
    run_config_status()


@status_app.command("pipeline")
def status_pipeline_command() -> None:
    """Show CodePipeline status details."""
    run_pipeline_status()


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

    run_init(
        customer_name=customer_name,
        workspace_dir=workspace_dir,
        aws_auth_type=aws_auth_type,
        aws_profile=aws_profile or None,
        aws_region=aws_region or None,
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

    run_import(
        customer_name=customer_name,
        workspace_dir=workspace_dir,
        config_dir=config_dir,
        aws_auth_type=aws_auth_type,
        aws_profile=aws_profile or None,
        aws_region=aws_region or None,
        lza_version=lza_version,
        dry_run=dry_run,
        force=force,
        skip_aws_check=skip_aws_check,
        interactive=_is_interactive(),
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
