"""CLI command and presentation for configuration repository status."""

from __future__ import annotations

from pathlib import Path

from rich.panel import Panel

from lza_workbench.cli.presentation import (
    console,
    print_info,
    print_kv,
    print_section,
)
from lza_workbench.workflows.status_config import (
    ConfigurationStatusResult,
    get_config_status_workflow,
)


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


def status_config_command(
    target_dir: Path | None = None,
) -> None:
    """Query workspace configuration metadata and display configuration status."""
    result = get_config_status_workflow(target_dir=target_dir)
    render_config_status(result, has_state=result.has_state)
