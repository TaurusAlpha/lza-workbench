"""CLI command and presentation for initializing local LZA configuration."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.cli import params
from lza_workbench.cli.output import (
    console,
    print_dry_run_header,
    print_info,
    print_kv,
    print_success,
    print_warning,
)
from lza_workbench.workflows.config_init import (
    ConfigInitResult,
    init_config_workflow,
)


def render_config_init_result(result: ConfigInitResult) -> None:
    """Render the results of configuration initialization."""
    workspace_dir = result.workspace_dir
    config_dir = result.config_dir
    template_name = result.template_source.source

    if result.dry_run:
        print_dry_run_header("lza config init")
        print_kv("Workspace", workspace_dir)
        print_kv("Template", template_name)
        print_kv("Config target", config_dir)
        console.print("Planned writes:")
        for path in result.written_paths:
            console.print(f"  - {path}")
        if result.unresolved_placeholders:
            print_warning(
                f"Unresolved placeholders ({len(result.unresolved_placeholders)}):"
            )
            for token in result.unresolved_placeholders:
                console.print(f"  - {token}")
        return

    print_success("Initialized LZA configuration")
    print_kv("Workspace", workspace_dir)
    print_kv("Template", template_name)
    print_kv("Config target", config_dir)
    print_kv("Files written", len(result.written_paths))

    if result.unresolved_placeholders:
        console.print()
        print_warning(
            f"Unresolved placeholders remaining ({len(result.unresolved_placeholders)}):"
        )
        for token in result.unresolved_placeholders:
            console.print(f"  - {token}")
        print_info(
            "Run 'lza installer init' to configure account emails, "
            "then 'lza config init --force' to resolve them.",
            dim=True,
        )


def config_init_command(
    *,
    template: params.ConfigTemplate = None,
    force: params.Force = False,
    dry_run: params.DryRun = False,
) -> None:
    """Initialize local LZA configuration in the current workspace from a packaged template."""
    result = init_config_workflow(
        target_dir=Path.cwd(),
        template_name=template,
        force=force,
        dry_run=dry_run,
    )
    render_config_init_result(result)
