"""Interface-neutral installer settings preparation and application workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lza_workbench.configuration.schema import get_canonical_config_s3_bucket
from lza_workbench.errors import LzaError
from lza_workbench.installer.config import validate_installer_configuration
from lza_workbench.installer.parameters import (
    UNSUPPORTED_INSTALLER_PARAMETERS,
    apply_installer_parameter,
    build_installer_cfn_parameters,
    get_installer_parameter_label,
    is_installer_parameter_applicable,
)
from lza_workbench.installer.templates import (
    inspect_template_parameters,
    resolve_installer_template,
    validate_parameters_against_schema,
)
from lza_workbench.workspace.config import write_workspace_config
from lza_workbench.workspace.context import WorkspaceCapability, load_workspace_context
from lza_workbench.workspace.schema import WorkspaceConfig
from lza_workbench.workspace.state import write_workspace_state


@dataclass(frozen=True)
class InstallerFormField:
    """One applicable CloudFormation parameter for an installer settings form."""

    name: str
    label: str
    default: str | None
    required: bool
    allowed_values: tuple[str, ...]
    allowed_pattern: str | None
    description: str | None


@dataclass(frozen=True)
class InstallerForm:
    """Template-derived installer settings form with no workspace persistence."""

    workspace_dir: Path
    template_path: Path
    fields: tuple[InstallerFormField, ...]
    resolved_parameters: dict[str, str]


@dataclass(frozen=True)
class InstallerSettingsRequest:
    """Resolved installer form values submitted by a CLI or future Web interface."""

    values: dict[str, str]
    target_dir: Path | None = None
    dry_run: bool = False
    no_save: bool = False


@dataclass(frozen=True)
class InstallerSettingsResult:
    """Applied installer settings ready for a subsequent plan or deployment."""

    workspace_dir: Path
    config: WorkspaceConfig
    template_path: Path
    resolved_parameters: dict[str, str]
    dry_run: bool
    no_save: bool


def _apply_values(config: WorkspaceConfig, values: dict[str, str]) -> None:
    for parameter_name, value in values.items():
        apply_installer_parameter(config, parameter_name, value)


def _ensure_canonical_s3_bucket(config: WorkspaceConfig, management_account_id: str | None) -> None:
    repository = config.configuration.repository
    if repository.type != "s3" or repository.bucket:
        return
    account_id = config.aws.account_id or management_account_id
    if account_id and config.aws.region:
        repository.bucket = get_canonical_config_s3_bucket(account_id, config.aws.region)


def _validate_candidate(config: WorkspaceConfig) -> WorkspaceConfig:
    """Run schema validation after codec assignments that use mutable models."""
    return WorkspaceConfig.model_validate(config.model_dump(mode="json"))


def get_installer_parameters_schema(
    *,
    target_dir: Path | None = None,
    values: dict[str, str] | None = None,
    dry_run: bool = False,
    all_fields: bool = False,
) -> InstallerForm:
    """Return applicable, template-derived fields without writing workspace config or state."""
    ctx = load_workspace_context(
        target_dir, required_capabilities=(WorkspaceCapability.METADATA_VALID,)
    )
    candidate = ctx.config.model_copy(deep=True)
    _apply_values(candidate, values or {})
    _ensure_canonical_s3_bucket(candidate, ctx.state.management_account_id if ctx.state else None)
    candidate = _validate_candidate(candidate)
    template_path = resolve_installer_template(ctx.workspace_dir, candidate, dry_run=dry_run)
    schema = inspect_template_parameters(template_path)
    resolved_parameters = build_installer_cfn_parameters(candidate, schema=schema)
    fields = tuple(
        InstallerFormField(
            name=name,
            label=get_installer_parameter_label(name, definition),
            default=resolved_parameters.get(name),
            required="Default" not in definition and not resolved_parameters.get(name),
            allowed_values=tuple(str(value) for value in definition.get("AllowedValues", [])),
            allowed_pattern=(
                str(definition["AllowedPattern"])
                if definition.get("AllowedPattern") is not None
                else None
            ),
            description=(str(definition["Description"]) if definition.get("Description") else None),
        )
        for name, definition in schema.items()
        if (
            name not in UNSUPPORTED_INSTALLER_PARAMETERS
            if all_fields
            else is_installer_parameter_applicable(candidate, name)
        )
    )
    return InstallerForm(
        workspace_dir=ctx.workspace_dir,
        template_path=template_path,
        fields=fields,
        resolved_parameters=resolved_parameters,
    )


def apply_installer_settings(request: InstallerSettingsRequest) -> InstallerSettingsResult:
    """Validate and persist already-resolved installer settings without prompting."""
    ctx = load_workspace_context(
        request.target_dir, required_capabilities=(WorkspaceCapability.METADATA_VALID,)
    )
    candidate = ctx.config.model_copy(deep=True)
    _apply_values(candidate, request.values)
    _ensure_canonical_s3_bucket(candidate, ctx.state.management_account_id if ctx.state else None)
    candidate = _validate_candidate(candidate)
    template_path = resolve_installer_template(
        ctx.workspace_dir, candidate, dry_run=request.dry_run
    )
    schema: dict[str, dict[str, Any]] = inspect_template_parameters(template_path)
    resolved_parameters = build_installer_cfn_parameters(candidate, schema=schema)
    validation = validate_installer_configuration(candidate)
    if not validation.is_complete:
        missing = ", ".join(
            f"{field.section}.{field.attribute}" for field in validation.missing_fields
        )
        raise LzaError(
            "Cannot initialize installer configuration; required configuration is missing: "
            f"{missing}."
        )
    validate_parameters_against_schema(resolved_parameters, schema)

    if not request.no_save and not request.dry_run:
        write_workspace_config(ctx.workspace_dir, candidate)
        ctx.state.installer_template_version = candidate.lza.version
        if template_path.exists():
            ctx.state.installer_downloaded_at = datetime.fromtimestamp(
                template_path.stat().st_mtime, tz=UTC
            )
        deployed = ctx.state.installer_deployed_parameters or {}
        changed = {
            k: v
            for k, v in resolved_parameters.items()
            if k not in deployed or deployed.get(k) != v
        }
        ctx.state.pending_installer_parameters = changed if changed else None
        write_workspace_state(ctx.workspace_dir, ctx.state)

    return InstallerSettingsResult(
        workspace_dir=ctx.workspace_dir,
        config=candidate,
        template_path=template_path,
        resolved_parameters=resolved_parameters,
        dry_run=request.dry_run,
        no_save=request.no_save,
    )


__all__ = [
    "InstallerForm",
    "InstallerFormField",
    "InstallerSettingsRequest",
    "InstallerSettingsResult",
    "apply_installer_settings",
    "get_installer_parameters_schema",
]
