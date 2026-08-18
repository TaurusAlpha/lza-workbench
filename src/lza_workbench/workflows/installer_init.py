"""Workflow for collecting and persisting installer configuration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from lza_workbench.errors import LzaError
from lza_workbench.installer.config import validate_installer_configuration
from lza_workbench.installer.parameters import (
    apply_installer_parameter,
    build_installer_cfn_parameters,
    persist_template_defaults,
)
from lza_workbench.installer.templates import (
    inspect_template_parameters,
    resolve_installer_template,
    validate_parameters_against_schema,
)
from lza_workbench.workspace.config import write_workspace_config
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context
from lza_workbench.workspace.schema import WorkspaceConfig


@dataclass(frozen=True)
class InstallerInitResult:
    """Resolved installer configuration ready for a subsequent plan or deployment."""

    workspace_dir: Path
    config: WorkspaceConfig
    template_path: Path
    resolved_parameters: dict[str, str]
    dry_run: bool


def initialize_installer_workflow(
    *,
    target_dir: Path | None = None,
    management_account_email: str | None = None,
    log_archive_account_email: str | None = None,
    audit_account_email: str | None = None,
    accelerator_prefix: str | None = None,
    prompter: Callable[[str, str | None], str] | None = None,
    dry_run: bool = False,
    no_save: bool = False,
) -> InstallerInitResult:
    """Collect template parameters, validate them, and persist accepted local settings."""
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.IMPORTED)
    workspace_dir, config = ctx.workspace_dir, ctx.config
    options = config.installer.options

    for provided, attribute in (
        (management_account_email, "management_account_email"),
        (log_archive_account_email, "log_archive_account_email"),
        (audit_account_email, "audit_account_email"),
    ):
        if provided and provided.strip():
            setattr(options, attribute, provided.strip())
    if accelerator_prefix and accelerator_prefix.strip():
        config.lza.accelerator_prefix = accelerator_prefix.strip()

    template_path = resolve_installer_template(workspace_dir, config, dry_run=dry_run)
    schema = inspect_template_parameters(template_path)
    persist_template_defaults(config, schema)
    resolved_parameters = build_installer_cfn_parameters(config, schema=schema)

    if prompter:
        for parameter_name, definition in schema.items():
            label = definition.get("Description") or parameter_name
            resolved_parameters = build_installer_cfn_parameters(config, schema=schema)
            value = prompter(f"{parameter_name}: {label}", resolved_parameters.get(parameter_name))
            apply_installer_parameter(config, parameter_name, value)
        resolved_parameters = build_installer_cfn_parameters(config, schema=schema)

    validation = validate_installer_configuration(config)
    if not validation.is_complete:
        missing = ", ".join(
            f"{field.section}.{field.attribute}" for field in validation.missing_fields
        )
        raise LzaError(
            "Cannot initialize installer configuration; required configuration is missing: "
            f"{missing}."
        )
    validate_parameters_against_schema(resolved_parameters, schema)

    if not no_save and not dry_run:
        write_workspace_config(workspace_dir, config)

    return InstallerInitResult(
        workspace_dir=workspace_dir,
        config=config,
        template_path=template_path,
        resolved_parameters=resolved_parameters,
        dry_run=dry_run,
    )


__all__ = ["InstallerInitResult", "initialize_installer_workflow"]
