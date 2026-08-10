"""Show installer stack status and synchronize state/config."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from lza_workbench.aws.client_factory import AwsClientFactory
from lza_workbench.aws.cloudformation import (
    CfnStackStatusResult,
    get_cloudformation_stack_status,
)
from lza_workbench.core.workspace import (
    WORKSPACE_CONFIG_FILE,
    WORKSPACE_STATE_FILE,
    WorkspaceConfig,
    WorkspaceReadinessLevel,
    WorkspaceState,
    build_installer_cfn_parameters,
    load_workspace_context,
    write_workspace_config,
    write_workspace_state,
)
from lza_workbench.utils.output import (
    console,
    print_info,
    print_kv,
    print_notice,
    print_section,
    print_success,
)


def extract_version_from_branch(branch: str) -> str:
    """Extract LZA version string from a Git/CodeCommit branch name."""
    cleaned = (branch or "").strip()
    if not cleaned:
        return "Unknown"
    if cleaned.startswith("release/"):
        cleaned = cleaned[len("release/") :]
    if cleaned in ("main", "master", "latest"):
        return "latest"
    if cleaned and not cleaned.startswith("v"):
        cleaned = f"v{cleaned}"
    return cleaned


def normalize_version(version: str) -> str:
    """Normalize version string for comparison (e.g. 1.16.0 -> v1.16.0)."""
    cleaned = (version or "").strip()
    if not cleaned or cleaned.lower() == "latest":
        return "latest"
    if not cleaned.lower().startswith("v"):
        return f"v{cleaned}"
    return cleaned


def run_installer_status(
    *,
    aws_profile: str | None = None,
    aws_region: str | None = None,
    sync_state: bool = False,
    sync_config: bool = False,
    target_dir: Path | None = None,
) -> None:
    """Query AWS CloudFormation and state file to display installer status."""
    if sync_config:
        sync_state = True

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

    cfn_stack_name = config.installer.stack_name or "AWSAccelerator-InstallerStack"
    cfn_client = factory.get_client("cloudformation") if factory else None
    cfn_status = get_cloudformation_stack_status(client=cfn_client, stack_name=cfn_stack_name)

    branch = (
        cfn_status.deployed_parameters.get("RepositoryBranchName", "") if cfn_status.exists else ""
    )
    deployed_version = extract_version_from_branch(branch)

    if sync_state:
        state = sync_installer_state(
            workspace_dir=workspace_dir,
            state=state or WorkspaceState.from_config(config),
            cfn_status=cfn_status,
            deployed_version=deployed_version,
        )

    if sync_config:
        config = sync_installer_config(
            workspace_dir=workspace_dir,
            config=config,
            cfn_status=cfn_status,
        )

    _render_status_report(
        workspace_dir=workspace_dir,
        config=config,
        state=state,
        profile=profile,
        region=region,
        aws_identity=aws_identity,
        aws_error=aws_error,
        cfn_status=cfn_status,
    )


def sync_installer_state(
    *,
    workspace_dir: Path,
    state: WorkspaceState,
    cfn_status: CfnStackStatusResult,
    deployed_version: str,
) -> WorkspaceState:
    """Synchronize .lza/state.json deployment metadata with current deployed AWS installer state."""
    if not cfn_status.exists:
        raise typer.BadParameter(
            "Cannot synchronize state: CloudFormation installer stack is not deployed "
            "or inaccessible."
        )

    now = datetime.now(UTC)
    state.installer_stack_id = cfn_status.stack_id
    state.installer_stack_status = cfn_status.stack_status
    state.installer_template_version = deployed_version
    state.updated_at = now

    write_workspace_state(workspace_dir / WORKSPACE_STATE_FILE, state)
    console.print(
        "[bold green]Synchronized .lza/state.json with live AWS installer state.[/bold green]"
    )
    return state


def sync_installer_config(
    *,
    workspace_dir: Path,
    config: WorkspaceConfig,
    cfn_status: CfnStackStatusResult,
) -> WorkspaceConfig:
    """Synchronize lza-workspace.yaml with deployed CloudFormation installer parameters."""
    if not cfn_status.exists or not cfn_status.deployed_parameters:
        raise typer.BadParameter(
            "Cannot synchronize config: CloudFormation installer stack is not deployed "
            "or has no parameters."
        )

    params = cfn_status.deployed_parameters

    if "RepositorySource" in params:
        source_type = params["RepositorySource"]
        if source_type in {"github", "codecommit", "s3", "codeconnection"}:
            config.installer.source_code.repository_type = source_type  # type: ignore[assignment]

    if "RepositoryOwner" in params:
        config.installer.source_code.owner = params["RepositoryOwner"]
    if "RepositoryName" in params:
        config.installer.source_code.repository_name = params["RepositoryName"]
    if "RepositoryBranchName" in params:
        branch = params["RepositoryBranchName"]
        config.installer.source_code.branch = branch
        extracted_ver = extract_version_from_branch(branch)
        if extracted_ver and extracted_ver != "Unknown":
            config.lza.version = extracted_ver

    if "ManagementAccountEmail" in params and params["ManagementAccountEmail"]:
        config.installer.options.management_account_email = params["ManagementAccountEmail"]
    if "LogArchiveAccountEmail" in params and params["LogArchiveAccountEmail"]:
        config.installer.options.log_archive_account_email = params["LogArchiveAccountEmail"]
    if "AuditAccountEmail" in params and params["AuditAccountEmail"]:
        config.installer.options.audit_account_email = params["AuditAccountEmail"]
    if "AcceleratorPrefix" in params and params["AcceleratorPrefix"]:
        config.lza.accelerator_prefix = params["AcceleratorPrefix"]

    if "ConfigurationRepositoryLocation" in params:
        repo_loc = params["ConfigurationRepositoryLocation"]
        if repo_loc in {"s3", "codecommit", "git"}:
            config.configuration.repository.type = repo_loc  # type: ignore[assignment]

    if "EnableApprovalStage" in params:
        config.installer.options.enable_approval_stage = params["EnableApprovalStage"] == "Yes"
    if "ControlTowerEnabled" in params:
        config.installer.options.control_tower_enabled = params["ControlTowerEnabled"] == "Yes"
    if "EnableDiagnosticsPack" in params:
        config.installer.options.enable_diagnostics_pack = params["EnableDiagnosticsPack"] == "Yes"
    if "UseExistingConfigRepo" in params:
        config.installer.options.use_existing_config_repo = params["UseExistingConfigRepo"] == "Yes"

    write_workspace_config(workspace_dir / WORKSPACE_CONFIG_FILE, config)
    print_success("Synchronized lza-workspace.yaml with deployed AWS installer configuration.")
    return config


def _render_status_report(
    *,
    workspace_dir: Path,
    config: WorkspaceConfig,
    state: WorkspaceState | None,
    profile: str,
    region: str,
    aws_identity: dict[str, str] | None,
    aws_error: str | None,
    cfn_status: CfnStackStatusResult,
) -> None:
    """Render rich status summary for installer stack."""
    console.print(
        Panel(f"[bold cyan]LZA Installer Status - {config.customer.name}[/bold cyan]", expand=False)
    )

    print_kv("Workspace", workspace_dir, bold_value=True)
    print_kv("Configured LZA Version", config.lza.version, bold_value=True)
    print_kv("AWS Profile", profile or "Not specified", bold_value=True)
    print_kv("AWS Region", region, bold_value=True)

    account_id = aws_identity["account"] if aws_identity else "UNKNOWN_ACCOUNT"

    if aws_identity:
        print_kv("AWS Account ID", account_id, style="green")
        print_kv("Caller Identity", aws_identity["arn"], style="dim")
    elif aws_error:
        print_notice(f"AWS Access Notice: {aws_error}")

    console.print()

    # Section 1: Stack & Pipeline Names / ARNs
    print_section(1, "CloudFormation Stack & Pipeline Resources")
    print_kv("Target Region", region, bold_value=True)

    cfn_stack_name = config.installer.stack_name or "AWSAccelerator-InstallerStack"
    expected_stack_arn = (
        cfn_status.stack_id
        or f"arn:aws:cloudformation:{region}:{account_id}:stack/{cfn_stack_name}/*"
    )
    print_kv("Installer CloudFormation Stack", cfn_stack_name, bold_value=True)
    print_kv("Installer Stack ARN", expected_stack_arn, style="dim")

    status_str = cfn_status.stack_status or "UNKNOWN"
    if cfn_status.exists:
        status_color = "green" if "COMPLETE" in status_str else "yellow"
    else:
        status_color = "red" if status_str == "UNKNOWN" else "dim"

    console.print(
        f"Installer Stack Status: [{status_color}][bold]{status_str}[/bold][/{status_color}]"
    )

    prefix = config.lza.accelerator_prefix or "AWSAccelerator"
    installer_pipeline_name = (
        config.pipelines.installer.name
        if hasattr(config.pipelines, "installer") and config.pipelines.installer.name
        else f"{prefix}-Installer"
    )
    installer_pipeline_arn = f"arn:aws:codepipeline:{region}:{account_id}:{installer_pipeline_name}"
    print_kv("Installer Pipeline Name", installer_pipeline_name, bold_value=True)
    print_kv("Installer Pipeline ARN", installer_pipeline_arn, style="dim")

    config_pipeline_name = config.pipelines.configuration.name or f"{prefix}-Pipeline"
    config_pipeline_arn = f"arn:aws:codepipeline:{region}:{account_id}:{config_pipeline_name}"
    print_kv("Config Pipeline Name", config_pipeline_name, bold_value=True)
    print_kv("Config Pipeline ARN", config_pipeline_arn, style="dim")

    if cfn_status.creation_time:
        print_kv("Stack Creation Time", cfn_status.creation_time)
    if cfn_status.last_updated_time:
        print_kv("Stack Last Updated", cfn_status.last_updated_time)

    if cfn_status.error:
        print_notice(f"CloudFormation Query Notice: {cfn_status.error}")

    # Section 2: Deployed Installer Details
    branch = (
        cfn_status.deployed_parameters.get("RepositoryBranchName", "") if cfn_status.exists else ""
    )
    deployed_version = extract_version_from_branch(branch) if branch else "Unknown"

    if cfn_status.exists and cfn_status.deployed_parameters:
        source_type = cfn_status.deployed_parameters.get(
            "RepositorySource", config.installer.source_code.repository_type
        )
        owner = cfn_status.deployed_parameters.get(
            "RepositoryOwner", config.installer.source_code.owner or "N/A"
        )
        repo_name = cfn_status.deployed_parameters.get(
            "RepositoryName", config.installer.source_code.repository_name or "N/A"
        )

        console.print()
        print_section(2, "Deployed Installer Details")
        print_kv("Deployed LZA Version", deployed_version, bold_value=True)
        print_kv("Source Type", source_type, bold_value=True)
        print_kv("Repository", f"{owner}/{repo_name}")
        print_kv("Branch", branch)

        norm_cfg = normalize_version(config.lza.version)
        norm_dep = normalize_version(deployed_version)
        if norm_cfg == norm_dep:
            print_kv("Version Match", "Match (Configured matches Deployed)", style="green")
        else:
            msg = f"Mismatch (Configured: {config.lza.version}, Deployed: {deployed_version})"
            print_kv("Version Match", msg, style="yellow")
    else:
        console.print()
        print_section(2, "Deployed Installer Details")
        print_kv("Source Type", config.installer.source_code.repository_type, bold_value=True)
        repo_name = config.installer.source_code.repository_name or "N/A"
        print_kv("Repository", repo_name)
        print_info("Deployed details unavailable (stack not deployed or unreadable).", dim=True)

    # Section 3: Configuration Drift
    console.print()
    print_section(3, "Configuration Drift")
    has_drift = False
    if cfn_status.exists and cfn_status.deployed_parameters:
        configured_params = build_installer_cfn_parameters(config)
        drift: dict[str, tuple[str, str]] = {}
        for key, cfg_val in configured_params.items():
            dep_val = cfn_status.deployed_parameters.get(key, "")
            if dep_val != cfg_val:
                drift[key] = (dep_val, cfg_val)

        if drift:
            has_drift = True
            drift_table = Table(title="Detected Parameter Drift", show_header=True)
            drift_table.add_column("Parameter Key", style="cyan")
            drift_table.add_column("Deployed Value", style="red")
            drift_table.add_column("Configured Value", style="green")
            for k, (d_val, c_val) in sorted(drift.items()):
                drift_table.add_row(k, str(d_val), str(c_val))
            console.print(drift_table)
        else:
            print_info("No configuration drift detected.", style="green")
    else:
        print_info("Drift check skipped (stack is not deployed).", dim=True)

    # Section 4: Stack Outputs
    console.print()
    print_section(4, "Stack Outputs")
    if cfn_status.outputs:
        out_table = Table(title="CloudFormation Outputs", show_header=True)
        out_table.add_column("Output Key", style="cyan")
        out_table.add_column("Output Value", style="white")
        for k, v in sorted(cfn_status.outputs.items()):
            out_table.add_row(k, str(v))
        console.print(out_table)
    else:
        print_info("No stack outputs available.", dim=True)

    # Section 5: Local State Metadata (.lza/state.json) & State Alignment
    console.print()
    print_section(5, "Local State Metadata (.lza/state.json)")
    state_out_of_sync = False
    if state:
        print_kv("State Stack ID", state.installer_stack_id or "Not recorded")
        print_kv("State Stack Status", state.installer_stack_status or "Not recorded")
        print_kv("State Stack Last Updated", state.installer_stack_updated_at or "Not recorded")
        print_kv("Installer Downloaded At", state.installer_downloaded_at or "Not recorded")
        print_kv("Installer Template Version", state.installer_template_version or "Not recorded")

        if cfn_status.exists:
            state_id_match = (
                state.installer_stack_id is None or state.installer_stack_id == cfn_status.stack_id
            )
            state_status_match = state.installer_stack_status == cfn_status.stack_status
            state_ver_match = normalize_version(
                state.installer_template_version or ""
            ) == normalize_version(deployed_version)

            if state_id_match and state_status_match and state_ver_match:
                align_msg = "In Sync (.lza/state.json matches live AWS state)"
                print_kv("State Alignment", align_msg, style="green")
            else:
                state_out_of_sync = True
                print_kv("State Alignment", "Out of Sync", style="yellow")
    else:
        print_info("No local state file found.", dim=True)

    # Recommended Next Commands at the very end of status report
    if cfn_status.exists and (has_drift or state_out_of_sync):
        console.print()
        console.print("[bold cyan]Recommended Next Command:[/bold cyan]")
        if has_drift:
            desc = "(Synchronizes lza-workspace.yaml and .lza/state.json with live AWS settings)"
            console.print(
                f"  [bold green]lza status installer --sync-config[/bold green]  [dim]{desc}[/dim]"
            )

            console.print(
                "  [bold green]lza installer deploy[/bold green]  "
                "[dim](Reconcile deployed installer stack with local configuration values)[/dim]"
            )
        elif state_out_of_sync:
            console.print(
                "  [bold green]lza status installer --sync-state[/bold green]   "
                "[dim](Synchronizes .lza/state.json with live AWS installer deployment state)[/dim]"
            )
