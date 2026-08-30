from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel

console = Console()


def format_timestamp(ts: Any) -> str | None:
    """Format any timestamp string or datetime object to standard 'YYYY-MM-DD HH:MM:SS UTC'."""
    if ts is None or ts == "" or ts == "None":
        return None
    if isinstance(ts, datetime):
        dt = ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)
        return dt.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    ts_str = str(ts).strip()
    if not ts_str:
        return None
    if ts_str.endswith(" UTC") and len(ts_str) == 23:
        return ts_str

    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return ts_str


def _humanize_status_text(status: str) -> str:
    """Convert raw AWS enum status like 'UPDATE_COMPLETE' to human friendly 'Update Complete'."""
    cfn_map = {
        "CREATE_COMPLETE": "Create Complete",
        "CREATE_IN_PROGRESS": "Create In Progress",
        "CREATE_FAILED": "Create Failed",
        "DELETE_COMPLETE": "Delete Complete",
        "DELETE_IN_PROGRESS": "Delete In Progress",
        "DELETE_FAILED": "Delete Failed",
        "UPDATE_COMPLETE": "Update Complete",
        "UPDATE_IN_PROGRESS": "Update In Progress",
        "UPDATE_COMPLETE_CLEANUP_IN_PROGRESS": "Update Cleanup In Progress",
        "UPDATE_FAILED": "Update Failed",
        "UPDATE_ROLLBACK_COMPLETE": "Update Rollback Complete",
        "UPDATE_ROLLBACK_IN_PROGRESS": "Update Rollback In Progress",
        "UPDATE_ROLLBACK_FAILED": "Update Rollback Failed",
        "ROLLBACK_COMPLETE": "Rollback Complete",
        "ROLLBACK_IN_PROGRESS": "Rollback In Progress",
        "ROLLBACK_FAILED": "Rollback Failed",
        "IMPORT_COMPLETE": "Import Complete",
        "IMPORT_IN_PROGRESS": "Import In Progress",
        "IMPORT_ROLLBACK_COMPLETE": "Import Rollback Complete",
        "AVAILABLE": "Available",
        "PENDING": "Pending",
    }
    return cfn_map.get(status, status)


def format_status(status: str | None) -> str:
    """Format a status with humanized wording and consistent Rich color tags."""
    if not status:
        return "[dim]Unknown[/dim]"

    human_text = _humanize_status_text(status)
    norm = human_text.lower()

    if any(
        k in norm
        for k in (
            "succeeded",
            "complete",
            "available",
            "clean",
            "in sync",
            "synchronized",
            "present",
            "exists",
            "match",
        )
    ):
        return f"[green]{human_text}[/green]"

    if any(
        k in norm
        for k in (
            "in progress",
            "inprogress",
            "building",
            "pending",
            "ahead",
            "behind",
            "dirty",
        )
    ):
        return f"[yellow]{human_text}[/yellow]"

    if any(
        k in norm
        for k in (
            "failed",
            "cancelled",
            "stopped",
            "missing",
            "inaccessible",
            "diverged",
            "out of sync",
            "mismatch",
            "error",
        )
    ):
        return f"[bold red]{human_text}[/bold red]"

    return f"[dim]{human_text}[/dim]"


def render_workspace_header(
    title: str,
    *,
    customer_name: str,
    workspace_dir: Path | str,
    lza_version: str | None = None,
    profile: str | None = None,
    region: str | None = None,
    aws_identity: dict[str, str] | None = None,
    aws_error: str | None = None,
) -> None:
    """Render the standard top-level workspace banner and context lines."""
    console.print(
        Panel(
            f"[bold cyan]{title} - {customer_name}[/bold cyan]",
            expand=False,
        )
    )
    print_kv("Workspace", workspace_dir, bold_value=True)
    if lza_version:
        print_kv("Configured LZA Version", lza_version, bold_value=True)
    print_kv("AWS Profile", profile or "Not specified", bold_value=True)
    print_kv("AWS Region", region or "Not specified", bold_value=True)

    if aws_identity:
        print_kv("AWS Account ID", aws_identity.get("account", "UNKNOWN"), style="green")
    elif aws_error:
        print_notice(f"AWS Access Notice: {aws_error}")


def render_failure_section(
    section_number: int,
    failed_actions: list[Any],
    error_message: str | None = None,
    *,
    verbose: bool = False,
) -> None:
    """Render standard failure section with normalized root cause diagnostics."""
    console.print()
    print_section(section_number, "Failure")
    if failed_actions:
        for fa in failed_actions:
            if getattr(fa, "stage_name", None):
                print_kv("Stage", fa.stage_name, bold_value=True)
            print_kv("Action", getattr(fa, "action_name", "Unknown"), bold_value=True)
            if getattr(fa, "failed_resource", None):
                print_kv("Resource", fa.failed_resource)

            diags = getattr(fa, "diagnostic_details", None)
            if diags:
                for diag in diags:
                    print_kv("Error", diag, style="red")
            else:
                err = getattr(fa, "error_message", None) or getattr(fa, "summary", None)
                if err:
                    print_kv("Error", err, style="red")

            if verbose and getattr(fa, "raw_diagnostic_details", None):
                console.print("  [dim]Raw Diagnostics:[/dim]")
                for raw in fa.raw_diagnostic_details:
                    console.print(f"    [dim]{raw}[/dim]")

            if getattr(fa, "external_execution_url", None):
                print_kv("Build Console", fa.external_execution_url, style="dim")
    elif error_message:
        print_kv("Error", error_message, style="red")


def print_success(message: str) -> None:
    """Print a bold green success message."""
    console.print(f"[bold green]{message}[/bold green]")


def print_dry_run_header(command_name: str) -> None:
    """Print standard dry-run title header."""
    console.print(f"[bold]Dry run: {command_name}[/bold]")


def print_warning(message: str) -> None:
    """Print a bold yellow warning message."""
    console.print(f"[bold yellow]{message}[/bold yellow]")


def print_notice(message: str) -> None:
    """Print a yellow notice message."""
    console.print(f"[yellow]{message}[/yellow]")


def print_error(message: str) -> None:
    """Print a bold red error message."""
    console.print(f"[bold red]{message}[/bold red]")


def print_info(message: str, dim: bool = False, style: str | None = None) -> None:
    """Print an informational message, optionally dimmed or styled."""
    if dim:
        console.print(f"[dim]{message}[/dim]")
    elif style:
        console.print(f"[{style}]{message}[/{style}]")
    else:
        console.print(message)


def print_section(number: int, title: str) -> None:
    """Print a numbered section heading."""
    console.print(f"[bold underline]{number}. {title}[/bold underline]")


def print_kv(label: str, value: Any, bold_value: bool = False, style: str | None = None) -> None:
    """Print a key-value pair line."""
    if bold_value:
        formatted_val = f"[bold]{value}[/bold]"
    elif style:
        formatted_val = f"[{style}]{value}[/{style}]"
    else:
        formatted_val = str(value)
    console.print(f"{label}: {formatted_val}")


def print_diff_summary(added: list[str], modified: list[str], removed: list[str]) -> None:
    """Print clean summary of added, modified, and removed files."""
    if not (added or modified or removed):
        console.print("[dim]No file changes detected (configuration up to date).[/dim]")
        return

    console.print(
        f"[bold]Changes: {len(added)} added, "
        f"{len(modified)} modified, {len(removed)} removed[/bold]"
    )
    for fname in added:
        console.print(f"  [green]+ {fname}[/green]")
    for fname in modified:
        console.print(f"  [yellow]~ {fname}[/yellow]")
    for fname in removed:
        console.print(f"  [red]- {fname}[/red]")


__all__ = [
    "console",
    "format_status",
    "format_timestamp",
    "print_diff_summary",
    "print_dry_run_header",
    "print_error",
    "print_info",
    "print_kv",
    "print_notice",
    "print_section",
    "print_success",
    "print_warning",
    "render_failure_section",
    "render_workspace_header",
]

