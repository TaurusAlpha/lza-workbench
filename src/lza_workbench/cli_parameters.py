"""Typer parameter declarations.

Define CLI names, aliases, help text, callbacks, and parameter types here.
"""

from pathlib import Path
from typing import Annotated

import typer

from lza_workbench import __version__


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"lza {__version__}")
        raise typer.Exit()


Version = Annotated[
    bool,
    typer.Option(
        "--version",
        "-v",
        callback=_version_callback,
        is_eager=True,
        help="Show the CLI version and exit.",
    ),
]

AwsProfile = Annotated[
    str,
    typer.Option("--aws-profile", help="AWS profile for the workspace."),
]

AwsRegion = Annotated[
    str,
    typer.Option("--aws-region", help="AWS region for the workspace."),
]

LzaVersion = Annotated[
    str | None,
    typer.Option("--lza-version", help="LZA version for the workspace."),
]

DryRun = Annotated[
    bool,
    typer.Option("--dry-run", help="Show planned actions without making changes."),
]

CustomerName = Annotated[
    str,
    typer.Argument(help="Customer name used for the workspace."),
]

WorkspaceDir = Annotated[
    Path | None,
    typer.Option(
        "--workspace-dir",
        help="Customer workspace directory.",
    ),
]

Force = Annotated[
    bool,
    typer.Option("--force", help="Reinitialize generated files in an existing workspace."),
]

SkipAwsCheck = Annotated[
    bool,
    typer.Option("--skip-aws-check", help="Skip STS caller identity validation."),
]

LzaConfigDir = Annotated[
    Path | None,
    typer.Option(
        "--lza-config-dir",
        help="Path to the existing LZA configuration directory (aws-accelerator-config).",
    ),
]

Extract = Annotated[
    bool,
    typer.Option("--extract", help="Extract downloaded configuration archives in workspace."),
]

ExecutePipeline = Annotated[
    bool,
    typer.Option(
        "--execute-pipeline",
        help="Trigger LZA CodePipeline execution after config upload.",
    ),
]
WatchPipeline = Annotated[
    bool,
    typer.Option(
        "--watch-pipeline",
        help="Monitor LZA CodePipeline execution until completion.",
    ),
]

