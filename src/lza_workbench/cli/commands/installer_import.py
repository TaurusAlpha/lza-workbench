"""CLI command and presentation for importing live AWS installer deployment."""

from __future__ import annotations

from pathlib import Path

from rich.table import Table

from lza_workbench.cli import params
from lza_workbench.cli.output import (
    console,
    format_status,
    print_dry_run_header,
    print_kv,
    print_section,
    print_success,
    render_workspace_header,
)
from lza_workbench.workflows.installer_import import (
    InstallerImportResult,
    import_installer_workflow,
)


def render_installer_import_result(result: InstallerImportResult) -> None:
    """Render the results of an installer import workflow."""
    if result.dry_run:
        print_dry_run_header("lza installer import")
        render_workspace_header(
            "LZA Installer Import (Dry Run)",
            customer_name=result.config.customer.name,
            workspace_dir=result.workspace_dir,
            lza_version=result.config.lza.version,
            profile=result.config.aws.profile,
            region=result.config.aws.region,
            aws_identity=result.aws_identity,
            aws_error=result.aws_error,
        )
        print_section(1, "Target Installer Stack")
        print_kv("Stack Name", result.stack_name, bold_value=True)
        print_kv("Stack Status", format_status(result.cfn_status.stack_status or "UNKNOWN"))
        print_kv("Deployed LZA Version", result.deployed_version or "N/A")
        if result.applied_parameters:
            table = Table(title="Discovered CloudFormation Parameters", show_header=True)
            table.add_column("Parameter Key", style="cyan")
            table.add_column("Parameter Value", style="green")
            for key, val in sorted(result.applied_parameters.items()):
                table.add_row(key, str(val))
            console.print(table)
        return

    print_success("Successfully imported live AWS installer deployment")
    render_workspace_header(
        "LZA Installer Import",
        customer_name=result.config.customer.name,
        workspace_dir=result.workspace_dir,
        lza_version=result.config.lza.version,
        profile=result.config.aws.profile,
        region=result.config.aws.region,
        aws_identity=result.aws_identity,
        aws_error=result.aws_error,
    )
    print_section(1, "Imported Stack & Parameters")
    print_kv("Installer Stack Name", result.stack_name, bold_value=True)
    print_kv("Stack Status", format_status(result.cfn_status.stack_status or "UNKNOWN"))
    print_kv("Deployed Version", result.deployed_version or "N/A", bold_value=True)
    print_kv(
        "Repository Source",
        result.config.installer.source_code.repository_type,
    )
    print_kv(
        "Config Location",
        result.config.configuration.repository.type,
    )
    if result.config.configuration.repository.bucket:
        print_kv("S3 Config Bucket", result.config.configuration.repository.bucket)
    if result.config.configuration.repository.repository_name:
        print_kv("Config Repo Name", result.config.configuration.repository.repository_name)

    console.print()
    console.print("[bold]Next steps:[/bold]")
    console.print("  - Run 'lza status installer' to inspect detailed installer status.")
    console.print("  - Run 'lza installer plan' to plan changes or updates.")


def installer_import_command(
    installer_stack_name: params.InstallerStackName = None,
    dry_run: params.DryRun = False,
    target_dir: Path | None = None,
) -> InstallerImportResult:
    """Import deployed CloudFormation installer stack parameters into local workspace."""
    result = import_installer_workflow(
        target_dir=target_dir,
        stack_name=installer_stack_name,
        dry_run=dry_run,
    )
    render_installer_import_result(result)
    return result


__all__ = [
    "installer_import_command",
    "render_installer_import_result",
]
