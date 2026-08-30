"""CLI command and presentation for LZA installer initialization."""

from __future__ import annotations

from pathlib import Path

from rich.panel import Panel

from lza_workbench.cli import params
from lza_workbench.cli.input import value_or_prompt
from lza_workbench.cli.output import (
    console,
    print_kv,
    print_notice,
)
from lza_workbench.workflows.installer_init import (
    InstallerInitResult,
    initialize_installer_workflow,
)


def render_installer_init_report(result: InstallerInitResult) -> None:
    """Render the local initialization result without inspecting AWS resources."""
    title = f"[bold cyan]LZA Installer Initialization - {result.config.customer.name}[/bold cyan]"
    if result.dry_run:
        title += " [yellow](Dry Run)[/yellow]"
    console.print(Panel(title, expand=False))
    print_kv("Workspace", result.workspace_dir, bold_value=True)
    print_kv("Template", result.template_path)
    print_kv("Resolved Parameters", len(result.resolved_parameters))
    if result.dry_run:
        print_notice("Dry run: installer configuration was not saved.")
    else:
        print_notice(
            "Installer configuration saved. Run `lza installer plan` to inspect AWS actions."
        )


def installer_init_command(
    management_account_email: str | None = None,
    log_archive_account_email: str | None = None,
    audit_account_email: str | None = None,
    accelerator_prefix: str | None = None,
    dry_run: params.DryRun = False,
    no_save: bool = False,
    target_dir: Path | None = None,
    interactive: bool = True,
) -> None:
    """Collect and persist installer configuration from the selected template."""

    def prompter(label: str, default: str | None) -> str:
        return value_or_prompt(
            label=label,
            value=None,
            default=default,
            interactive=interactive,
        )

    result = initialize_installer_workflow(
        target_dir=target_dir,
        management_account_email=management_account_email,
        log_archive_account_email=log_archive_account_email,
        audit_account_email=audit_account_email,
        accelerator_prefix=accelerator_prefix,
        prompter=prompter if interactive else None,
        dry_run=dry_run,
        no_save=no_save,
    )
    render_installer_init_report(result)


__all__ = [
    "installer_init_command",
    "render_installer_init_report",
]
