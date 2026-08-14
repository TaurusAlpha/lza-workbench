"""Show detailed configuration source status for current workspace."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich.panel import Panel

from lza_workbench.utils.output import (
    console,
    print_info,
    print_kv,
    print_section,
)
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context


@dataclass(frozen=True)
class ConfigurationStatusResult:
    """All data needed to render configuration-source status."""

    workspace_dir: Path
    customer_name: str
    lza_version: str
    config_dir: Path
    config_dir_exists: bool
    yaml_files: tuple[str, ...]
    repository_type: str
    repository_bucket: str | None
    repository_prefix: str
    repository_key: str
    repository_name: str | None
    repository_branch: str | None
    uploaded_at: object | None
    downloaded_at: object | None


def run_config_status(
    *,
    target_dir: Path | None = None,
) -> None:
    """Query workspace configuration metadata and display configuration status."""
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED)
    workspace_dir, config, state = ctx.workspace_dir, ctx.config, ctx.state

    config_dir = workspace_dir / config.configuration.local_path
    yaml_files = (
        tuple(
            sorted(
                file.name
                for file in config_dir.iterdir()
                if file.is_file() and file.suffix in (".yaml", ".yml")
            )
        )
        if config_dir.exists()
        else ()
    )
    repo = config.configuration.repository
    result = ConfigurationStatusResult(
        workspace_dir=workspace_dir,
        customer_name=config.customer.name,
        lza_version=config.lza.version,
        config_dir=config_dir,
        config_dir_exists=config_dir.exists(),
        yaml_files=yaml_files,
        repository_type=repo.type,
        repository_bucket=repo.bucket,
        repository_prefix=repo.prefix,
        repository_key=repo.key,
        repository_name=repo.repository_name,
        repository_branch=repo.branch,
        uploaded_at=state.config_uploaded_at if state else None,
        downloaded_at=state.config_downloaded_at if state else None,
    )
    render_config_status(result, has_state=state is not None)


def render_config_status(result: ConfigurationStatusResult, *, has_state: bool) -> None:
    """Render prepared configuration status without inspecting the workspace."""
    console.print(
        Panel(
            f"[bold cyan]LZA Configuration Status - {result.customer_name}[/bold cyan]",
            expand=False,
        )
    )

    print_kv("Workspace", result.workspace_dir, bold_value=True)
    print_kv("Configured LZA Version", result.lza_version, bold_value=True)

    exists_str = "[green]Present[/green]" if result.config_dir_exists else "[red]Missing[/red]"
    print_kv("Local Config Path", f"{result.config_dir} ({exists_str})")

    if result.config_dir_exists:
        print_kv("YAML Config Files Count", len(result.yaml_files))
        if result.yaml_files:
            print_kv("Files Found", ", ".join(result.yaml_files), style="dim")

    console.print()
    print_section(1, "Configuration Repository Settings")
    print_kv("Repository Type", result.repository_type, bold_value=True)

    if result.repository_type == "s3":
        s3_bucket = result.repository_bucket or "Not set"
        s3_prefix = result.repository_prefix or "Not set"
        s3_key = result.repository_key or "Not set"
        print_kv("S3 Bucket", s3_bucket)
        print_kv("S3 Key Prefix", f"{s3_prefix}/{s3_key}")
    elif result.repository_type == "codecommit":
        print_kv("Repository Name", result.repository_name or "Not set")
        print_kv("Branch", result.repository_branch or "main")
    elif result.repository_type == "git":
        print_kv("Git Repository", result.repository_name or "Not set")
        print_kv("Branch", result.repository_branch or "main")

    console.print()
    print_section(2, "Upload / Download State Metadata")
    if has_state:
        print_kv("Last Uploaded At", result.uploaded_at or "Never")
        print_kv("Last Downloaded At", result.downloaded_at or "Never")
    else:
        print_info("No local state file found (.lza/state.json).", dim=True)
