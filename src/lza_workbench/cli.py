"""LZA Workbench command-line interface.

Define the CLI entrypoint and command workflows for workspace management.
"""

from __future__ import annotations

import sys

import typer

from lza_workbench import cli_parameters as params
from lza_workbench.commands.config_download import run_download_config
from lza_workbench.commands.config_upload import run_upload_config
from lza_workbench.commands.installer_download import run_download_installer
from lza_workbench.commands.installer_plan import run_installer_plan
from lza_workbench.commands.installer_status import run_installer_status
from lza_workbench.commands.workspace_import import run_import
from lza_workbench.commands.workspace_init import run_init
from lza_workbench.core.workspace import resolve_init_workspace_dir

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


@installer_app.command("plan")
def installer_plan_command(
    dry_run: params.DryRun = False,
    no_save: bool = False,
) -> None:
    """Resolve and persist installer configuration, then show the actions required to deploy."""
    run_installer_plan(
        dry_run=dry_run,
        no_save=no_save,
        interactive=_is_interactive(),
    )


app.add_typer(config_app, name="config")
app.add_typer(installer_app, name="installer")


def _is_interactive() -> bool:
    return sys.stdin.isatty()


@app.callback()
def root(version: params.Version = False) -> None:
    """Run LZA Workbench."""


@app.command("init")
def init_command(
    customer_name: params.CustomerName,
    workspace_dir: params.WorkspaceDir = None,
    aws_profile: params.AwsProfile = "",
    aws_region: params.AwsRegion = "",
    lza_version: params.LzaVersion = None,
    dry_run: params.DryRun = False,
    force: params.Force = False,
    skip_aws_check: params.SkipAwsCheck = True,
) -> None:
    """Create a new customer-specific LZA workspace."""
    interactive = _is_interactive()

    resolved_workspace_dir = resolve_init_workspace_dir(
        customer_name=customer_name,
        workspace_dir=workspace_dir,
        interactive=interactive,
    )

    run_init(
        customer_name=customer_name,
        workspace_dir=resolved_workspace_dir,
        aws_profile=aws_profile or None,
        aws_region=aws_region or None,
        lza_version=lza_version,
        dry_run=dry_run,
        force=force,
        skip_aws_check=skip_aws_check,
        interactive=interactive,
    )


@app.command("import")
def import_command(
    customer_name: params.CustomerName,
    workspace_dir: params.WorkspaceDir = None,
    config_dir: params.LzaConfigDir = None,
    aws_profile: params.AwsProfile = "",
    aws_region: params.AwsRegion = "",
    lza_version: params.LzaVersion = None,
    dry_run: params.DryRun = False,
    force: params.Force = False,
    skip_aws_check: params.SkipAwsCheck = True,
) -> None:
    """Adopt an existing customer-owned LZA configuration."""
    run_import(
        customer_name=customer_name,
        workspace_dir=workspace_dir,
        config_dir=config_dir,
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
    force: params.Force = True,
    extract: params.Extract = True,
) -> None:
    """Download LZA configuration from configured repository source."""
    run_download_config(
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
    run_upload_config(
        dry_run=dry_run,
        interactive=_is_interactive(),
    )


@installer_app.command("download")
def installer_download_command(
    lza_version: params.LzaVersion = None,
    dry_run: params.DryRun = False,
    force: params.Force = False,
) -> None:
    """Download LZA installer CloudFormation template into customer workspace."""
    run_download_installer(
        lza_version=lza_version,
        dry_run=dry_run,
        force=force,
        interactive=_is_interactive(),
    )


@installer_app.command("status")
def installer_status_command(
    aws_profile: params.AwsProfile = "",
    aws_region: params.AwsRegion = "",
    sync_state: params.SyncState = False,
    sync_config: params.SyncConfig = False,
) -> None:
    """Show the current installer deployment state."""
    run_installer_status(
        aws_profile=aws_profile or None,
        aws_region=aws_region or None,
        sync_state=sync_state,
        sync_config=sync_config,
    )


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a process-style exit code."""
    try:
        app(args=argv, standalone_mode=False)
    except typer.Exit as exc:
        return int(exc.exit_code or 0)
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
