from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from lza_workbench import __version__
from lza_workbench.commands.import_workspace import (CONFIG_DIRECTORY_NAME,
                                                     collect_import_request,
                                                     resolve_import_workspace,
                                                     run_import,
                                                     validate_import_config)
from lza_workbench.commands.init import (collect_init_request,
                                         resolve_init_project_dir, run_init)

app = typer.Typer(
    help="LZA Workbench CLI",
    no_args_is_help=True,
    add_completion=False,
)


def _is_interactive() -> bool:
    return sys.stdin.isatty()


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"lza {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-v",
            callback=_version_callback,
            is_eager=True,
            help="Show the CLI version and exit.",
        ),
    ] = False,
) -> None:
    """Run LZA Workbench."""


@app.command("init")
def init_command(
    customer_name: Annotated[str, typer.Argument(help="Customer name used for the workspace.")],
    workspace_dir: Annotated[
        Path | None,
        typer.Option(
            "--workspace-dir",
            "-w",
            help="Customer workspace directory to create.",
        ),
    ] = None,
    aws_profile: Annotated[
        str | None,
        typer.Option("--aws-profile", help="AWS profile to store and validate."),
    ] = None,
    aws_region: Annotated[
        str | None,
        typer.Option("--aws-region", help="AWS region to store and validate."),
    ] = None,
    lza_version: Annotated[
        str | None,
        typer.Option("--lza-version", help="LZA version for this customer workspace."),
    ] = None,
    template_source: Annotated[
        str | None,
        typer.Option(
            "--template-source",
            help="Template source. Use 'default' or a local template path.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show planned actions without writing files."),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Reinitialize generated files in an existing workspace."),
    ] = False,
    skip_aws_check: Annotated[
        bool,
        typer.Option("--skip-aws-check", help="Skip STS caller identity validation."),
    ] = False,
) -> None:
    """Create a new customer-specific LZA project workspace."""
    interactive = _is_interactive()
    project_dir = resolve_init_project_dir(
        customer_name=customer_name,
        workspace_dir=workspace_dir,
        interactive=interactive,
    )
    candidate_config = project_dir / CONFIG_DIRECTORY_NAME
    if not force and (candidate_config.exists() or candidate_config.is_symlink()):
        _, config_dir = resolve_import_workspace(project_dir)
        validate_import_config(config_dir)
        if not interactive:
            raise typer.BadParameter(
                f"Target directory contains an existing LZA configuration: {project_dir}. "
                f"Run `lza import {project_dir}` to adopt it."
            )
        if not typer.confirm("Existing LZA configuration detected. Import this workspace?"):
            typer.echo("Import cancelled; no changes were made.")
            return
        if template_source is not None:
            typer.echo(
                "The selected template source is ignored; import preserves the existing "
                "customer configuration."
            )
        request = collect_import_request(
            workspace=project_dir,
            customer_name=customer_name,
            aws_profile=aws_profile,
            aws_region=aws_region,
            lza_version=lza_version,
            dry_run=dry_run,
            interactive=interactive,
        )
        run_import(request)
        return

    request = collect_init_request(
        customer_name=customer_name,
        workspace_dir=project_dir,
        aws_profile=aws_profile,
        aws_region=aws_region,
        lza_version=lza_version,
        template_source=template_source,
        dry_run=dry_run,
        force=force,
        skip_aws_check=skip_aws_check,
        interactive=interactive,
    )
    run_init(request)


@app.command("import")
def import_command(
    workspace: Annotated[
        Path | None,
        typer.Argument(
            help=("Existing workspace root defaults to the current directory.")
        ),
    ] = None,
    customer_name: Annotated[
        str | None,
        typer.Option("--customer-name", help="Customer name to store in project metadata."),
    ] = None,
    aws_profile: Annotated[
        str | None,
        typer.Option("--aws-profile", help="AWS profile to store without validating it."),
    ] = None,
    aws_region: Annotated[
        str | None,
        typer.Option("--aws-region", help="AWS region to store."),
    ] = None,
    lza_version: Annotated[
        str | None,
        typer.Option("--lza-version", help="LZA version to store."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show metadata changes without writing files."),
    ] = False,
) -> None:
    """Adopt an existing customer-owned LZA configuration."""
    request = collect_import_request(
        workspace=workspace,
        customer_name=customer_name,
        aws_profile=aws_profile,
        aws_region=aws_region,
        lza_version=lza_version,
        dry_run=dry_run,
        interactive=_is_interactive(),
    )
    run_import(request)


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
