"""LZA Workbench command-line interface.

Define the CLI entrypoint and command workflows for workspace initialization and import.
Define CLI commands here
"""

from __future__ import annotations

import sys

import typer

from lza_workbench import cli_parameters as params
from lza_workbench.commands.import_workspace import (
    CONFIG_DIRECTORY_NAME,
    collect_import_options,
    resolve_import_workspace,
    run_import,
    validate_import_config,
)
from lza_workbench.commands.init import (
    collect_init_options,
    resolve_init_workspace_dir,
    run_init,
)

app = typer.Typer(
    help="LZA Workbench CLI",
    no_args_is_help=True,
    add_completion=False,
)


def _is_interactive() -> bool:
    return sys.stdin.isatty()


@app.callback()
def root(version: params.Version = False) -> None:
    """Run LZA Workbench."""


@app.command("init")
def init_command(
    customer_name: params.CustomerName,
    workspace_dir: params.WorkspaceDir = None,
    aws_profile: params.AwsProfile = None,
    aws_region: params.AwsRegion = None,
    lza_version: params.LzaVersion = None,
    template_source: params.TemplateSource = None,
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
    candidate_config = resolved_workspace_dir / CONFIG_DIRECTORY_NAME
    if not force and (candidate_config.exists() or candidate_config.is_symlink()):
        _, config_dir = resolve_import_workspace(resolved_workspace_dir)
        validate_import_config(config_dir)
        if not interactive:
            raise typer.BadParameter(
                "Target directory contains an existing LZA configuration: "
                f"{resolved_workspace_dir}. "
                "Run `lza import "
                f"{customer_name} --workspace-dir {resolved_workspace_dir}` to adopt it."
            )
        if not typer.confirm("Existing LZA configuration detected. Import this workspace?"):
            typer.echo("Import cancelled; no changes were made.")
            return
        if template_source is not None:
            typer.echo(
                "The selected template source is ignored; import preserves the existing "
                "customer configuration."
            )
        request = collect_import_options(
            workspace_dir=resolved_workspace_dir,
            customer_name=customer_name,
            aws_profile=aws_profile,
            aws_region=aws_region,
            lza_version=lza_version,
            dry_run=dry_run,
            interactive=interactive,
        )
        run_import(request)
        return

    request = collect_init_options(
        customer_name=customer_name,
        workspace_dir=resolved_workspace_dir,
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
    customer_name: params.CustomerName,
    workspace_dir: params.WorkspaceDir = None,
    aws_profile: params.AwsProfile = None,
    aws_region: params.AwsRegion = None,
    lza_version: params.LzaVersion = None,
    dry_run: params.DryRun = False,
) -> None:
    """Adopt an existing customer-owned LZA configuration."""
    request = collect_import_options(
        workspace_dir=workspace_dir,
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
