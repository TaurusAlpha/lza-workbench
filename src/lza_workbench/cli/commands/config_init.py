"""CLI command and presentation for initializing local LZA configuration."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.cli import params
from lza_workbench.cli.input import value_or_prompt
from lza_workbench.cli.output import (
    console,
    print_dry_run_header,
    print_info,
    print_kv,
    print_success,
    print_warning,
)
from lza_workbench.configuration.templates import (
    DEFAULT_TEMPLATE_SOURCE,
    list_packaged_templates,
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

    if result.skipped:
        if result.is_managed:
            init_str = (
                result.initialized_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                if result.initialized_at
                else "previously"
            )
            print_info(
                f"Configuration directory '{config_dir}' already exists "
                f"(initialized from template '{template_name}' on {init_str})."
            )
            if result.drifted_fields:
                drifted_str = ", ".join(result.drifted_fields)
                print_warning(
                    f"Workspace settings changed since initialization ({drifted_str}). "
                    "Run 'lza config init --force' to re-apply the template with "
                    "current workspace settings."
                )
            else:
                print_info(
                    "Use 'lza config init --force' to re-initialize or overwrite.",
                    dim=True,
                )
        else:
            print_warning(
                f"Configuration directory '{config_dir}' already exists "
                "(unmanaged or manually created). "
                f"Use 'lza config init --force' to overwrite with template '{template_name}'."
            )
        return

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
        if result.config.configuration.repository.type == "s3" and not result.git_skipped:
            console.print("Planned Git initialization:")
            console.print("  - Initialize local Git repository")
            console.print("  - Create initial commit")
        elif result.git_skipped and result.git_skip_reason:
            print_info(f"Git repository: Skipped ({result.git_skip_reason})", dim=True)
        return

    print_success("Initialized LZA configuration")
    print_kv("Workspace", workspace_dir)
    print_kv("Template", template_name)
    print_kv("Config target", config_dir)
    print_kv("Files written", len(result.written_paths))
    if result.git_initialized and result.git_committed:
        print_kv("Git repository", "Initialized with initial commit")
    elif result.git_skipped and result.git_skip_reason:
        print_kv("Git repository", f"Skipped ({result.git_skip_reason})", style="dim")

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
    resolved_template = template
    if resolved_template is None:
        packaged = list_packaged_templates()
        if len(packaged) == 1:
            resolved_template = packaged[0]
        elif len(packaged) > 1:
            default_template = (
                DEFAULT_TEMPLATE_SOURCE if DEFAULT_TEMPLATE_SOURCE in packaged else packaged[0]
            )
            console.print("Available configuration templates:")
            for idx, name in enumerate(packaged, start=1):
                console.print(f"  {idx}. {name}")

            def _validate_choice(val: str) -> str:
                val = val.strip()
                if val in packaged:
                    return val
                if val.isdigit():
                    idx = int(val)
                    if 1 <= idx <= len(packaged):
                        return packaged[idx - 1]
                raise ValueError(
                    f"Invalid template choice '{val}'. Choose from: {', '.join(packaged)}"
                )

            resolved_template = value_or_prompt(
                "Select configuration template",
                value=None,
                default=default_template,
                interactive=True,
                validator=_validate_choice,
            )

    result = init_config_workflow(
        target_dir=Path.cwd(),
        template_name=resolved_template,
        force=force,
        dry_run=dry_run,
    )
    render_config_init_result(result)
