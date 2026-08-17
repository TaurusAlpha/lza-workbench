"""Show installer stack status and run explicit state/config synchronization actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from rich.panel import Panel
from rich.table import Table

from lza_workbench.aws.cloudformation import CfnStackStatusResult, get_cloudformation_stack_status
from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.errors import LzaError
from lza_workbench.installer.status import (
    StateAlignment,
    calculate_configuration_drift,
    calculate_state_alignment,
)
from lza_workbench.installer.versions import branch_to_version, normalize_lza_version
from lza_workbench.utils.output import (
    console,
    print_info,
    print_kv,
    print_notice,
    print_section,
    print_success,
)
from lza_workbench.workspace.config import write_workspace_config
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context
from lza_workbench.workspace.models import WorkspaceConfig, WorkspaceState
from lza_workbench.workspace.state import write_workspace_state


@dataclass(frozen=True)
class InstallerStatusResult:
    """All data required to render an installer status report."""

    workspace_dir: Path
    config: WorkspaceConfig
    state: WorkspaceState | None
    profile: str
    region: str
    aws_identity: dict[str, str] | None
    aws_error: str | None
    cfn_status: CfnStackStatusResult
    deployed_version: str
    configuration_drift: dict[str, tuple[str, str]]
    state_alignment: StateAlignment | None
    installer_pipeline_name: str
    config_pipeline_name: str


def run_installer_status(
    *, sync_state: bool = False, sync_config: bool = False, target_dir: Path | None = None
) -> None:
    """Query AWS, optionally synchronize, then render an installer status result."""
    if sync_config:
        sync_state = True

    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED)
    workspace_dir, config, state = ctx.workspace_dir, ctx.config, ctx.state
    aws_context = resolve_aws_execution_context(config.aws)
    cfn_stack_name = config.installer.stack_name or "AWSAccelerator-InstallerStack"
    cfn_client = aws_context.factory.get_client("cloudformation") if aws_context.identity else None
    cfn_status = get_cloudformation_stack_status(client=cfn_client, stack_name=cfn_stack_name)
    deployed_version = branch_to_version(
        cfn_status.deployed_parameters.get("RepositoryBranchName", "") if cfn_status.exists else ""
    )

    if sync_state:
        state = sync_installer_state(
            workspace_dir=workspace_dir,
            state=state or WorkspaceState.from_config(config),
            cfn_status=cfn_status,
            deployed_version=deployed_version,
        )
    if sync_config:
        config = sync_installer_config(
            workspace_dir=workspace_dir, config=config, cfn_status=cfn_status
        )

    result = prepare_installer_status(
        workspace_dir=workspace_dir,
        config=config,
        state=state,
        profile=config.aws.profile or "",
        region=aws_context.region,
        aws_identity=aws_context.identity,
        aws_error=aws_context.error,
        cfn_status=cfn_status,
    )
    render_installer_status(result)


def prepare_installer_status(
    *,
    workspace_dir: Path,
    config: WorkspaceConfig,
    state: WorkspaceState | None,
    profile: str,
    region: str,
    aws_identity: dict[str, str] | None,
    aws_error: str | None,
    cfn_status: CfnStackStatusResult,
) -> InstallerStatusResult:
    """Prepare report data without calling AWS, writing files, or rendering output."""
    deployed_version = branch_to_version(
        cfn_status.deployed_parameters.get("RepositoryBranchName", "") if cfn_status.exists else ""
    )
    drift = (
        calculate_configuration_drift(config, cfn_status.deployed_parameters)
        if cfn_status.exists and cfn_status.deployed_parameters
        else {}
    )
    alignment = (
        calculate_state_alignment(
            state,
            stack_id=cfn_status.stack_id,
            stack_status=cfn_status.stack_status,
            deployed_version=deployed_version,
        )
        if state and cfn_status.exists
        else None
    )
    prefix = config.lza.accelerator_prefix or "AWSAccelerator"
    return InstallerStatusResult(
        workspace_dir=workspace_dir,
        config=config,
        state=state,
        profile=profile,
        region=region,
        aws_identity=aws_identity,
        aws_error=aws_error,
        cfn_status=cfn_status,
        deployed_version=deployed_version,
        configuration_drift=drift,
        state_alignment=alignment,
        installer_pipeline_name=config.pipelines.installer.name or f"{prefix}-Installer",
        config_pipeline_name=config.pipelines.configuration.name or f"{prefix}-Pipeline",
    )


def sync_installer_state(
    *,
    workspace_dir: Path,
    state: WorkspaceState,
    cfn_status: CfnStackStatusResult,
    deployed_version: str,
) -> WorkspaceState:
    """Synchronize .lza/state.json deployment metadata with live installer state."""
    if not cfn_status.exists:
        raise LzaError(
            "Cannot synchronize state: CloudFormation installer stack is not deployed "
            "or inaccessible."
        )
    state.installer_stack_id = cfn_status.stack_id
    state.installer_stack_status = cfn_status.stack_status
    state.installer_template_version = deployed_version
    state.updated_at = datetime.now(UTC)
    write_workspace_state(workspace_dir, state)
    console.print(
        "[bold green]Synchronized .lza/state.json with live AWS installer state.[/bold green]"
    )
    return state


def sync_installer_config(
    *, workspace_dir: Path, config: WorkspaceConfig, cfn_status: CfnStackStatusResult
) -> WorkspaceConfig:
    """Synchronize lza-workspace.yaml with deployed installer parameters."""
    if not cfn_status.exists or not cfn_status.deployed_parameters:
        raise LzaError(
            "Cannot synchronize config: CloudFormation installer stack is not deployed "
            "or has no parameters."
        )
    params = cfn_status.deployed_parameters
    source_type = params.get("RepositorySource")
    if source_type in {"github", "codecommit", "s3", "codeconnection"}:
        config.installer.source_code.repository_type = cast(
            Literal["github", "codecommit", "s3", "codeconnection"], source_type
        )
    config.installer.source_code.owner = params.get(
        "RepositoryOwner", config.installer.source_code.owner
    )
    config.installer.source_code.repository_name = params.get(
        "RepositoryName", config.installer.source_code.repository_name
    )
    if branch := params.get("RepositoryBranchName"):
        config.installer.source_code.branch = branch
        if (version := branch_to_version(branch)) != "Unknown":
            config.lza.version = version
    for parameter, attribute in (
        ("ManagementAccountEmail", "management_account_email"),
        ("LogArchiveAccountEmail", "log_archive_account_email"),
        ("AuditAccountEmail", "audit_account_email"),
    ):
        if value := params.get(parameter):
            setattr(config.installer.options, attribute, value)
    if prefix := params.get("AcceleratorPrefix"):
        config.lza.accelerator_prefix = prefix
    repo_type = params.get("ConfigurationRepositoryLocation")
    if repo_type in {"s3", "codecommit", "codeconnection", "git"}:
        config.configuration.repository.type = cast(
            Literal["s3", "codecommit", "codeconnection", "git"], repo_type
        )
    if "EnableApprovalStage" in params:
        config.installer.options.enable_approval_stage = params["EnableApprovalStage"] == "Yes"
        config.installer.options.approval_stage_notify_email_list = (
            params.get("ApprovalStageNotifyEmailList", "").split(",")
            if params.get("ApprovalStageNotifyEmailList")
            else []
        )
    for parameter, attribute in (
        ("ControlTowerEnabled", "control_tower_enabled"),
        ("EnableDiagnosticsPack", "enable_diagnostics_pack"),
        ("UseExistingConfigRepo", "use_existing_config_repo"),
    ):
        if parameter in params:
            setattr(config.installer.options, attribute, params[parameter] == "Yes")
    write_workspace_config(workspace_dir, config)
    print_success("Synchronized lza-workspace.yaml with deployed AWS installer configuration.")
    return config


def render_installer_status(result: InstallerStatusResult) -> None:
    """Render prepared installer data without AWS calls or workspace writes."""
    console.print(
        Panel(
            f"[bold cyan]LZA Installer Status - {result.config.customer.name}[/bold cyan]",
            expand=False,
        )
    )
    print_kv("Workspace", result.workspace_dir, bold_value=True)
    print_kv("Configured LZA Version", result.config.lza.version, bold_value=True)
    print_kv("AWS Profile", result.profile or "Not specified", bold_value=True)
    print_kv("AWS Region", result.region, bold_value=True)
    if result.aws_identity:
        print_kv("AWS Account ID", result.aws_identity["account"], style="green")
        print_kv("Caller Identity", result.aws_identity["arn"], style="dim")
    elif result.aws_error:
        print_notice(f"AWS Access Notice: {result.aws_error}")
    _render_resources(result)
    _render_deployed_details(result)
    _render_drift(result)
    _render_outputs(result)
    _render_state_alignment(result)
    _render_recommendations(result)


def _render_resources(result: InstallerStatusResult) -> None:
    console.print()
    print_section(1, "CloudFormation Stack & Pipeline Resources")
    status = result.cfn_status.stack_status or "UNKNOWN"
    account_id = result.aws_identity["account"] if result.aws_identity else "UNKNOWN_ACCOUNT"
    stack_name = result.config.installer.stack_name or "AWSAccelerator-InstallerStack"
    stack_arn = (
        result.cfn_status.stack_id
        or f"arn:aws:cloudformation:{result.region}:{account_id}:stack/{stack_name}/*"
    )
    color = (
        "green"
        if result.cfn_status.exists and "COMPLETE" in status
        else "yellow"
        if result.cfn_status.exists
        else "red"
        if status == "UNKNOWN"
        else "dim"
    )
    print_kv("Target Region", result.region, bold_value=True)
    print_kv("Installer CloudFormation Stack", stack_name, bold_value=True)
    print_kv("Installer Stack ARN", stack_arn, style="dim")
    console.print(f"Installer Stack Status: [{color}][bold]{status}[/bold][/{color}]")
    for label, name in (
        ("Installer", result.installer_pipeline_name),
        ("Config", result.config_pipeline_name),
    ):
        print_kv(f"{label} Pipeline Name", name, bold_value=True)
        print_kv(
            f"{label} Pipeline ARN",
            f"arn:aws:codepipeline:{result.region}:{account_id}:{name}",
            style="dim",
        )
    if result.cfn_status.creation_time:
        print_kv("Stack Creation Time", result.cfn_status.creation_time)
    if result.cfn_status.last_updated_time:
        print_kv("Stack Last Updated", result.cfn_status.last_updated_time)
    if result.cfn_status.error:
        print_notice(f"CloudFormation Query Notice: {result.cfn_status.error}")


def _render_deployed_details(result: InstallerStatusResult) -> None:
    console.print()
    print_section(2, "Deployed Installer Details")
    params = result.cfn_status.deployed_parameters
    if not result.cfn_status.exists or not params:
        print_kv(
            "Source Type", result.config.installer.source_code.repository_type, bold_value=True
        )
        print_kv("Repository", result.config.installer.source_code.repository_name or "N/A")
        print_info("Deployed details unavailable (stack not deployed or unreadable).", dim=True)
        return
    print_kv("Deployed LZA Version", result.deployed_version, bold_value=True)
    print_kv(
        "Source Type",
        params.get("RepositorySource", result.config.installer.source_code.repository_type),
        bold_value=True,
    )
    owner = params.get("RepositoryOwner", result.config.installer.source_code.owner or "N/A")
    repository_name = params.get(
        "RepositoryName", result.config.installer.source_code.repository_name or "N/A"
    )
    print_kv("Repository", f"{owner}/{repository_name}")
    print_kv("Branch", params.get("RepositoryBranchName", ""))
    matches = normalize_lza_version(result.config.lza.version) == normalize_lza_version(
        result.deployed_version
    )
    print_kv(
        "Version Match",
        "Match (Configured matches Deployed)"
        if matches
        else (
            f"Mismatch (Configured: {result.config.lza.version}, "
            f"Deployed: {result.deployed_version})"
        ),
        style="green" if matches else "yellow",
    )


def _render_drift(result: InstallerStatusResult) -> None:
    console.print()
    print_section(3, "Configuration Drift")
    if not result.cfn_status.exists or not result.cfn_status.deployed_parameters:
        print_info("Drift check skipped (stack is not deployed).", dim=True)
        return
    if not result.configuration_drift:
        print_info("No configuration drift detected.", style="green")
        return
    table = Table(title="Detected Parameter Drift", show_header=True)
    table.add_column("Parameter Key", style="cyan")
    table.add_column("Deployed Value", style="red")
    table.add_column("Configured Value", style="green")
    for key, (deployed, configured) in sorted(result.configuration_drift.items()):
        table.add_row(key, deployed, configured)
    console.print(table)


def _render_outputs(result: InstallerStatusResult) -> None:
    console.print()
    print_section(4, "Stack Outputs")
    if not result.cfn_status.outputs:
        print_info("No stack outputs available.", dim=True)
        return
    table = Table(title="CloudFormation Outputs", show_header=True)
    table.add_column("Output Key", style="cyan")
    table.add_column("Output Value", style="white")
    for key, value in sorted(result.cfn_status.outputs.items()):
        table.add_row(key, value)
    console.print(table)


def _render_state_alignment(result: InstallerStatusResult) -> None:
    console.print()
    print_section(5, "Local State Metadata (.lza/state.json)")
    if not result.state:
        print_info("No local state file found.", dim=True)
        return
    state = result.state
    for label, value in (
        ("State Stack ID", state.installer_stack_id),
        ("State Stack Status", state.installer_stack_status),
        ("State Stack Last Updated", state.installer_stack_updated_at),
        ("Installer Downloaded At", state.installer_downloaded_at),
        ("Installer Template Version", state.installer_template_version),
    ):
        print_kv(label, value or "Not recorded")
    if result.state_alignment:
        print_kv(
            "State Alignment",
            "In Sync (.lza/state.json matches live AWS state)"
            if result.state_alignment.in_sync
            else "Out of Sync",
            style="green" if result.state_alignment.in_sync else "yellow",
        )


def _render_recommendations(result: InstallerStatusResult) -> None:
    state_out_of_sync = result.state_alignment is not None and not result.state_alignment.in_sync
    if not result.cfn_status.exists or (not result.configuration_drift and not state_out_of_sync):
        return
    console.print()
    console.print("[bold cyan]Recommended Next Command:[/bold cyan]")
    if result.configuration_drift:
        console.print(
            "  [bold green]lza status installer --sync-config[/bold green]  "
            "[dim](Synchronizes lza-workspace.yaml and .lza/state.json "
            "with live AWS settings)[/dim]"
        )
        console.print(
            "  [bold green]lza installer deploy[/bold green]  "
            "[dim](Reconcile deployed installer stack with local configuration values)[/dim]"
        )
    else:
        console.print(
            "  [bold green]lza status installer --sync-state[/bold green]   "
            "[dim](Synchronizes .lza/state.json with live AWS installer deployment state)[/dim]"
        )
