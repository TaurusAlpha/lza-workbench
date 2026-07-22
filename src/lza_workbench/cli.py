from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from lza_workbench import __version__
from lza_workbench.commands.init import collect_init_request, run_init

app = typer.Typer(
    help="LZA Workbench CLI",
    no_args_is_help=True,
    add_completion=False,
)


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
    request = collect_init_request(
        customer_name=customer_name,
        workspace_dir=workspace_dir,
        aws_profile=aws_profile,
        aws_region=aws_region,
        lza_version=lza_version,
        template_source=template_source,
        dry_run=dry_run,
        force=force,
        skip_aws_check=skip_aws_check,
        interactive=sys.stdin.isatty(),
    )
    run_init(request)


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
