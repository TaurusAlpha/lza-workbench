"""Show detailed pipeline status for current workspace."""

from __future__ import annotations

from pathlib import Path

from rich.panel import Panel

from lza_workbench.aws.client_factory import AwsClientFactory
from lza_workbench.core.workspace import (
    WorkspaceReadinessLevel,
    load_workspace_context,
)
from lza_workbench.utils.output import (
    console,
    print_info,
    print_kv,
    print_notice,
    print_section,
)


def run_pipeline_status(
    *,
    aws_profile: str | None = None,
    aws_region: str | None = None,
    target_dir: Path | None = None,
) -> None:
    """Query AWS CodePipeline state for current workspace pipelines."""
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED)
    workspace_dir, config, state = ctx.workspace_dir, ctx.config, ctx.state

    profile = (aws_profile or "").strip() or (config.aws.profile or "").strip()
    region = (aws_region or "").strip() or (config.aws.region or "").strip() or "us-east-1"

    factory = None
    aws_identity = None
    aws_error = None
    if profile:
        try:
            factory = AwsClientFactory(profile, region)
            aws_identity = factory.validate_identity()
        except Exception as exc:  # noqa: BLE001
            aws_error = str(exc)

    account_id = aws_identity["account"] if aws_identity else "UNKNOWN_ACCOUNT"

    console.print(
        Panel(
            f"[bold cyan]LZA Pipeline Status - {config.customer.name}[/bold cyan]",
            expand=False,
        )
    )

    print_kv("Workspace", workspace_dir, bold_value=True)
    print_kv("AWS Profile", profile or "Not specified", bold_value=True)
    print_kv("AWS Region", region, bold_value=True)

    if aws_identity:
        print_kv("AWS Account ID", account_id, style="green")
    elif aws_error:
        print_notice(f"AWS Access Notice: {aws_error}")

    prefix = config.lza.accelerator_prefix or "AWSAccelerator"

    # Section 1: Installer Pipeline
    console.print()
    print_section(1, "Installer Pipeline")
    installer_pipeline_name = (
        config.pipelines.installer.name
        if hasattr(config.pipelines, "installer") and config.pipelines.installer.name
        else f"{prefix}-Installer"
    )
    installer_pipeline_arn = f"arn:aws:codepipeline:{region}:{account_id}:{installer_pipeline_name}"
    print_kv("Pipeline Name", installer_pipeline_name, bold_value=True)
    print_kv("Pipeline ARN", installer_pipeline_arn, style="dim")

    # Section 2: Configuration Pipeline
    console.print()
    print_section(2, "Configuration Pipeline")
    config_pipeline_name = config.pipelines.configuration.name or f"{prefix}-Pipeline"
    config_pipeline_arn = f"arn:aws:codepipeline:{region}:{account_id}:{config_pipeline_name}"
    print_kv("Pipeline Name", config_pipeline_name, bold_value=True)
    print_kv("Pipeline ARN", config_pipeline_arn, style="dim")

    # Section 3: Execution Metadata
    console.print()
    print_section(3, "Execution History Metadata (.lza/state.json)")
    if state:
        last_exec_id = getattr(state, "pipeline_execution_id", None) or "None recorded"
        print_kv("Last Recorded Execution ID", last_exec_id)
    else:
        print_info("No local state file found (.lza/state.json).", dim=True)
