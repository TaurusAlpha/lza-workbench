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
    InstallerSettingsRequest,
    InstallerSettingsResult,
    apply_installer_settings,
    get_installer_parameters_schema,
)


def render_installer_init_report(result: InstallerSettingsResult) -> None:
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
    elif result.no_save:
        print_notice("Installer configuration was not saved.")
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
    values = {
        name: value.strip()
        for name, value in {
            "ManagementAccountEmail": management_account_email,
            "LogArchiveAccountEmail": log_archive_account_email,
            "AuditAccountEmail": audit_account_email,
            "AcceleratorPrefix": accelerator_prefix,
        }.items()
        if value and value.strip()
    }
    if interactive:
        while True:
            form = get_installer_parameters_schema(
                target_dir=target_dir, values=values, dry_run=dry_run
            )
            next_field = next((field for field in form.fields if field.name not in values), None)
            if next_field is None:
                break
            values[next_field.name] = value_or_prompt(
                label=next_field.label,
                value=None,
                default=next_field.default,
                interactive=True,
            )

    result = apply_installer_settings(
        InstallerSettingsRequest(
            target_dir=target_dir,
            values=values,
            dry_run=dry_run,
            no_save=no_save,
        )
    )
    render_installer_init_report(result)


__all__ = [
    "installer_init_command",
    "render_installer_init_report",
]
