"""Shared Rich CLI output helpers, prompts, and presentation primitives."""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console

from lza_workbench.errors import LzaError

console = Console()


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


def value_or_prompt(
    label: str, value: str | None, default: str | None = None, interactive: bool = True
) -> str:
    """Use an explicit value, prompt with a default, or use that default."""
    if value:
        return value
    if interactive:
        if default is not None:
            return typer.prompt(label, default=default)
        return typer.prompt(label)
    if default is not None:
        return default
    raise LzaError(f"{label} is required.")
