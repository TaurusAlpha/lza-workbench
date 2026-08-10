"""Show detailed configuration source status for current workspace."""

from __future__ import annotations

from pathlib import Path

from rich.panel import Panel

from lza_workbench.core.workspace import (
    WorkspaceReadinessLevel,
    load_workspace_context,
)
from lza_workbench.utils.output import (
    console,
    print_info,
    print_kv,
    print_section,
)


def run_config_status(
    *,
    target_dir: Path | None = None,
) -> None:
    """Query workspace configuration metadata and display configuration status."""
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED)
    workspace_dir, config, state = ctx.workspace_dir, ctx.config, ctx.state

    console.print(
        Panel(
            f"[bold cyan]LZA Configuration Status - {config.customer.name}[/bold cyan]",
            expand=False,
        )
    )

    print_kv("Workspace", workspace_dir, bold_value=True)
    print_kv("Configured LZA Version", config.lza.version, bold_value=True)

    config_dir = workspace_dir / config.configuration.local_path
    exists_str = "[green]Present[/green]" if config_dir.exists() else "[red]Missing[/red]"
    print_kv("Local Config Path", f"{config_dir} ({exists_str})")

    if config_dir.exists():
        files = [
            f.name for f in config_dir.iterdir() if f.is_file() and f.suffix in (".yaml", ".yml")
        ]
        print_kv("YAML Config Files Count", len(files))
        if files:
            print_kv("Files Found", ", ".join(sorted(files)), style="dim")

    console.print()
    print_section(1, "Configuration Repository Settings")
    repo_config = config.configuration.repository
    print_kv("Repository Type", repo_config.type, bold_value=True)

    if repo_config.type == "s3":
        s3_bucket = repo_config.bucket or "Not set"
        s3_prefix = repo_config.prefix or "Not set"
        s3_key = repo_config.key or "Not set"
        print_kv("S3 Bucket", s3_bucket)
        print_kv("S3 Key Prefix", f"{s3_prefix}/{s3_key}")
    elif repo_config.type == "codecommit":
        print_kv("Repository Name", repo_config.repository or "Not set")
        print_kv("Branch", repo_config.branch or "main")
    elif repo_config.type == "git":
        print_kv("Git Repository", repo_config.repository or "Not set")
        print_kv("Branch", repo_config.branch or "main")

    console.print()
    print_section(2, "Upload / Download State Metadata")
    if state:
        uploaded_at = getattr(state, "config_uploaded_at", None) or "Never"
        downloaded_at = getattr(state, "config_downloaded_at", None) or "Never"
        print_kv("Last Uploaded At", uploaded_at)
        print_kv("Last Downloaded At", downloaded_at)
    else:
        print_info("No local state file found (.lza/state.json).", dim=True)
