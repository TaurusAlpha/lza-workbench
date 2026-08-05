"""Show the current LZA installer deployment state."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
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
    WorkspaceState,
    build_installer_cfn_parameters,
    load_workspace_config,
    load_workspace_state,
    resolve_workspace_dir,
)

console = Console()


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
    target_dir: Path | None = None,
) -> None:
    """Query AWS CloudFormation and state file to display installer status."""
    workspace_dir = resolve_workspace_dir(target_dir)
    config = load_workspace_config(workspace_dir / WORKSPACE_CONFIG_FILE)

    state: WorkspaceState | None = None
    state_file = workspace_dir / WORKSPACE_STATE_FILE
    if state_file.exists():
        try:
            state = load_workspace_state(state_file)
        except Exception:  # noqa: BLE001
            state = None

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
    cfn_status = get_cloudformation_stack_status(factory=factory, stack_name=cfn_stack_name)

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

    console.print(f"Workspace: [bold]{workspace_dir}[/bold]")
    console.print(f"Configured LZA Version: [bold]{config.lza.version}[/bold]")
    console.print(f"AWS Profile: [bold]{profile or 'Not specified'}[/bold]")
    console.print(f"AWS Region: [bold]{region}[/bold]")

    account_id = aws_identity["account"] if aws_identity else "UNKNOWN_ACCOUNT"

    if aws_identity:
        console.print(f"AWS Account ID: [green]{account_id}[/green]")
        console.print(f"Caller Identity: [dim]{aws_identity['arn']}[/dim]")
    elif aws_error:
        console.print(f"[yellow]AWS Access Notice: {aws_error}[/yellow]")

    console.print()

    # Section 1: Stack & Pipeline Names / ARNs
    console.print("[bold underline]1. CloudFormation Stack & Pipeline Resources[/bold underline]")
    console.print(f"Target Region: [bold]{region}[/bold]")

    # CloudFormation Stack
    cfn_stack_name = config.installer.stack_name or "AWSAccelerator-InstallerStack"
    expected_stack_arn = (
        cfn_status.stack_id
        or f"arn:aws:cloudformation:{region}:{account_id}:stack/{cfn_stack_name}/*"
    )
    console.print(f"Installer CloudFormation Stack: [bold]{cfn_stack_name}[/bold]")
    console.print(f"Installer Stack ARN: [dim]{expected_stack_arn}[/dim]")

    status_str = cfn_status.stack_status or "UNKNOWN"
    if cfn_status.exists:
        status_color = "green" if "COMPLETE" in status_str else "yellow"
    else:
        status_color = "red" if status_str == "UNKNOWN" else "dim"

    console.print(
        f"Installer Stack Status: [{status_color}][bold]{status_str}[/bold][/{status_color}]"
    )

    # Installer Pipeline (CodePipeline)
    prefix = config.lza.accelerator_prefix or "AWSAccelerator"
    installer_pipeline_name = (
        config.pipelines.installer.name
        if hasattr(config.pipelines, "installer") and config.pipelines.installer.name
        else f"{prefix}-Installer"
    )
    installer_pipeline_arn = f"arn:aws:codepipeline:{region}:{account_id}:{installer_pipeline_name}"
    console.print(f"Installer Pipeline Name: [bold]{installer_pipeline_name}[/bold]")
    console.print(f"Installer Pipeline ARN: [dim]{installer_pipeline_arn}[/dim]")

    # Configuration Pipeline (CodePipeline)
    config_pipeline_name = config.pipelines.configuration.name or f"{prefix}-Pipeline"
    config_pipeline_arn = f"arn:aws:codepipeline:{region}:{account_id}:{config_pipeline_name}"
    console.print(f"Config Pipeline Name: [bold]{config_pipeline_name}[/bold]")
    console.print(f"Config Pipeline ARN: [dim]{config_pipeline_arn}[/dim]")

    if cfn_status.creation_time:
        console.print(f"Stack Creation Time: {cfn_status.creation_time}")
    if cfn_status.last_updated_time:
        console.print(f"Stack Last Updated: {cfn_status.last_updated_time}")

    if cfn_status.error:
        console.print(f"[yellow]CloudFormation Query Notice: {cfn_status.error}[/yellow]")

    # Section 2: Deployed Installer Details
    if cfn_status.exists and cfn_status.deployed_parameters:
        branch = cfn_status.deployed_parameters.get("RepositoryBranchName", "")
        deployed_version = extract_version_from_branch(branch)
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
        console.print("[bold underline]2. Deployed Installer Details[/bold underline]")
        console.print(f"Deployed LZA Version: [bold]{deployed_version}[/bold]")
        console.print(f"Source Type: [bold]{source_type}[/bold]")
        console.print(f"Repository: {owner}/{repo_name}")
        console.print(f"Branch: {branch}")

        norm_cfg = normalize_version(config.lza.version)
        norm_dep = normalize_version(deployed_version)
        if norm_cfg == norm_dep:
            console.print("Version Match: [green]Match (Configured matches Deployed)[/green]")
        else:
            console.print(
                f"Version Match: [yellow]Mismatch (Configured: {config.lza.version}, Deployed: {deployed_version})[/yellow]"
            )
    else:
        console.print()
        console.print("[bold underline]2. Deployed Installer Details[/bold underline]")
        console.print(
            "Source Type: [bold]" + config.installer.source_code.repository_type + "[/bold]"
        )
        repo_name = config.installer.source_code.repository_name or "N/A"
        console.print(f"Repository: {repo_name}")
        console.print("[dim]Deployed details unavailable (stack not deployed or unreadable).[/dim]")

    # Section 3: Configuration Drift
    console.print()
    console.print("[bold underline]3. Configuration Drift[/bold underline]")
    if cfn_status.exists and cfn_status.deployed_parameters:
        configured_params = build_installer_cfn_parameters(config)
        drift: dict[str, tuple[str, str]] = {}
        for key, cfg_val in configured_params.items():
            dep_val = cfn_status.deployed_parameters.get(key, "")
            if dep_val != cfg_val:
                drift[key] = (dep_val, cfg_val)

        if drift:
            drift_table = Table(title="Detected Parameter Drift", show_header=True)
            drift_table.add_column("Parameter Key", style="cyan")
            drift_table.add_column("Deployed Value", style="red")
            drift_table.add_column("Configured Value", style="green")
            for k, (d_val, c_val) in sorted(drift.items()):
                drift_table.add_row(k, str(d_val), str(c_val))
            console.print(drift_table)
        else:
            console.print("[green]No configuration drift detected.[/green]")
    else:
        console.print("[dim]Drift check skipped (stack is not deployed).[/dim]")

    # Section 4: Stack Outputs
    console.print()
    console.print("[bold underline]4. Stack Outputs[/bold underline]")
    if cfn_status.outputs:
        out_table = Table(title="CloudFormation Outputs", show_header=True)
        out_table.add_column("Output Key", style="cyan")
        out_table.add_column("Output Value", style="white")
        for k, v in sorted(cfn_status.outputs.items()):
            out_table.add_row(k, str(v))
        console.print(out_table)
    else:
        console.print("[dim]No stack outputs available.[/dim]")

    # Section 5: State File Metadata (.lza/state.json)
    console.print()
    console.print("[bold underline]5. Local State Metadata (.lza/state.json)[/bold underline]")
    if state:
        console.print(f"State Stack ID: {state.installer_stack_id or 'Not recorded'}")
        console.print(f"State Stack Status: {state.installer_stack_status or 'Not recorded'}")
        console.print(
            f"State Stack Last Updated: {state.installer_stack_updated_at or 'Not recorded'}"
        )
        console.print(f"Installer Downloaded At: {state.installer_downloaded_at or 'Not recorded'}")
        console.print(
            f"Installer Template Version: {state.installer_template_version or 'Not recorded'}"
        )
    else:
        console.print("[dim]No local state file found.[/dim]")
