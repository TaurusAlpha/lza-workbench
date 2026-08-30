"""Typer parameter declarations.

Define CLI names, aliases, help text, callbacks, and parameter types here.
"""

from __future__ import annotations

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

AwsAuthType = Annotated[
    str,
    typer.Option(
        "--aws-auth-type", help="AWS authentication type for the workspace (default: profile)."
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

PrimeCredentials = Annotated[
    bool,
    typer.Option(
        "--prime-credentials",
        help="Use prime credentials for AWS operations. Used when opt-region is configured.",
    ),
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

ImportWorkspaceDir = Annotated[
    Path,
    typer.Argument(help="Existing workspace directory; use . for the current directory."),
]

ImportCustomerName = Annotated[
    str | None,
    typer.Option("--customer-name", help="Customer name stored in workspace metadata."),
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

Repair = Annotated[
    bool,
    typer.Option("--repair", help="Repair missing, partial, or corrupted workspace metadata."),
]

SkipAwsCheck = Annotated[
    bool,
    typer.Option("--skip-aws-check", help="Skip STS caller identity validation."),
]

InstallerStackName = Annotated[
    str | None,
    typer.Option(
        "--installer-stack-name",
        "--stack-name",
        help="CloudFormation installer stack name (default: AWSAccelerator-InstallerStack).",
    ),
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
    typer.Option(
        "--extract/--no-extract",
        help="Extract downloaded configuration archives in workspace.",
    ),
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

SyncState = Annotated[
    bool,
    typer.Option(
        "--sync-state",
        help="Synchronize .lza/state.json with live AWS installer state.",
    ),
]

SyncConfig = Annotated[
    bool,
    typer.Option(
        "--sync-config",
        help="Synchronize lza-workspace.yaml with deployed CloudFormation installer configuration.",
    ),
]

ManagementAccountEmail = Annotated[
    str | None,
    typer.Option(
        "--management-account-email",
        "-m",
        help="Management (primary) account email address.",
    ),
]

LogArchiveAccountEmail = Annotated[
    str | None,
    typer.Option(
        "--log-archive-account-email",
        "-l",
        help="Log Archive account email address.",
    ),
]

AuditAccountEmail = Annotated[
    str | None,
    typer.Option(
        "--audit-account-email",
        "-a",
        help="Security Audit account email address.",
    ),
]

AcceleratorPrefix = Annotated[
    str | None,
    typer.Option(
        "--accelerator-prefix",
        help="Prefix value for accelerator deployed resources (default: AWSAccelerator).",
    ),
]

ConfigTemplate = Annotated[
    str | None,
    typer.Option(
        "--template",
        "-t",
        help="Packaged configuration template name or path.",
    ),
]

NoWatch = Annotated[
    bool,
    typer.Option(
        "--no-watch",
        help="Do not wait for pipeline execution to complete.",
    ),
]

PipelineName = Annotated[
    str | None,
    typer.Option(
        "--pipeline-name",
        "-p",
        help="Name of the LZA CodePipeline to execute or monitor.",
    ),
]

ExecutionId = Annotated[
    str | None,
    typer.Option(
        "--execution-id",
        "-e",
        help="Specific pipeline execution ID to monitor.",
    ),
]

PollInterval = Annotated[
    int | None,
    typer.Option(
        "--poll-interval",
        help="Interval in seconds between pipeline status checks.",
    ),
]

Verbose = Annotated[
    bool,
    typer.Option(
        "--verbose",
        "-v",
        help="Show detailed execution breakdown and diagnostic output.",
    ),
]

GithubToken = Annotated[
    str | None,
    typer.Option(
        "--github-token",
        help="GitHub Personal Access Token to store in AWS Secrets Manager.",
    ),
]

AllowMissingGithubSecret = Annotated[
    bool,
    typer.Option(
        "--allow-missing-github-secret",
        help="Allow bootstrap to proceed with a warning if the GitHub token secret does not exist.",
    ),
]
