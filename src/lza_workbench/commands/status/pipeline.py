"""Show detailed pipeline status for current workspace."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich.panel import Panel

from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.utils.output import (
    console,
    print_info,
    print_kv,
    print_notice,
    print_section,
)
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context


@dataclass(frozen=True)
class PipelineStatusResult:
    """Prepared pipeline names, ARNs, and execution metadata for rendering."""

    workspace_dir: Path
    customer_name: str
    profile: str
    region: str
    aws_identity: dict[str, str] | None
    aws_error: str | None
    installer_pipeline_name: str
    installer_pipeline_arn: str
    config_pipeline_name: str
    config_pipeline_arn: str
    installer_execution_id: str | None
    config_execution_id: str | None


def run_pipeline_status(
    *,
    target_dir: Path | None = None,
) -> None:
    """Query AWS CodePipeline state for current workspace pipelines."""
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED)
    workspace_dir, config, state = ctx.workspace_dir, ctx.config, ctx.state

    profile = config.aws.profile or ""
    region = config.aws.region

    aws_context = resolve_aws_execution_context(config.aws)
    region = aws_context.region
    aws_identity = aws_context.identity
    aws_error = aws_context.error

    account_id = aws_identity["account"] if aws_identity else "UNKNOWN_ACCOUNT"
    prefix = config.lza.accelerator_prefix or "AWSAccelerator"
    installer_pipeline_name = config.pipelines.installer.name or f"{prefix}-Installer"
    config_pipeline_name = config.pipelines.configuration.name or f"{prefix}-Pipeline"
    result = PipelineStatusResult(
        workspace_dir=workspace_dir,
        customer_name=config.customer.name,
        profile=profile,
        region=region,
        aws_identity=aws_identity,
        aws_error=aws_error,
        installer_pipeline_name=installer_pipeline_name,
        installer_pipeline_arn=f"arn:aws:codepipeline:{region}:{account_id}:{installer_pipeline_name}",
        config_pipeline_name=config_pipeline_name,
        config_pipeline_arn=f"arn:aws:codepipeline:{region}:{account_id}:{config_pipeline_name}",
        installer_execution_id=state.installer_pipeline_execution_id if state else None,
        config_execution_id=state.config_pipeline_execution_id if state else None,
    )
    render_pipeline_status(result, has_state=state is not None)


def render_pipeline_status(result: PipelineStatusResult, *, has_state: bool) -> None:
    """Render prepared pipeline status without AWS calls or workspace reads."""

    console.print(
        Panel(
            f"[bold cyan]LZA Pipeline Status - {result.customer_name}[/bold cyan]",
            expand=False,
        )
    )

    print_kv("Workspace", result.workspace_dir, bold_value=True)
    print_kv("AWS Profile", result.profile or "Not specified", bold_value=True)
    print_kv("AWS Region", result.region, bold_value=True)

    if result.aws_identity:
        print_kv("AWS Account ID", result.aws_identity["account"], style="green")
    elif result.aws_error:
        print_notice(f"AWS Access Notice: {result.aws_error}")

    # Section 1: Installer Pipeline
    console.print()
    print_section(1, "Installer Pipeline")
    print_kv("Pipeline Name", result.installer_pipeline_name, bold_value=True)
    print_kv("Pipeline ARN", result.installer_pipeline_arn, style="dim")

    # Section 2: Configuration Pipeline
    console.print()
    print_section(2, "Configuration Pipeline")
    print_kv("Pipeline Name", result.config_pipeline_name, bold_value=True)
    print_kv("Pipeline ARN", result.config_pipeline_arn, style="dim")

    # Section 3: Execution Metadata
    console.print()
    print_section(3, "Execution History Metadata (.lza/state.json)")
    if has_state:
        print_kv("Last Installer Execution ID", result.installer_execution_id or "None recorded")
        print_kv("Last Configuration Execution ID", result.config_execution_id or "None recorded")
    else:
        print_info("No local state file found (.lza/state.json).", dim=True)
