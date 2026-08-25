"""Workflow for importing and adopting an existing LZA workspace."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lza_workbench.configuration.archive import count_config_files
from lza_workbench.configuration.git import (
    GitProvenance,
    resolve_git_provenance,
)
from lza_workbench.configuration.schema import (
    ConfigurationConfig,
    ConfigurationRepositoryConfig,
    ConfigurationTemplateConfig,
    PackagingExcludeConfig,
)
from lza_workbench.configuration.templates import validate_template
from lza_workbench.configuration.validation import (
    validate_lza_configuration_schema,
    validate_yaml_syntax,
)
from lza_workbench.errors import LzaError
from lza_workbench.workflows.status_installer import get_installer_status_workflow
from lza_workbench.workspace.config import (
    WORKSPACE_CONFIG_FILE,
    load_workspace_config,
    write_workspace_config,
)
from lza_workbench.workspace.paths import normalize_customer_slug
from lza_workbench.workspace.schema import (
    AwsConfig,
    CustomerConfig,
    LzaConfig,
    WorkspaceConfig,
    WorkspaceState,
)
from lza_workbench.workspace.state import (
    WORKSPACE_STATE_FILE,
    load_workspace_state,
    write_workspace_state,
)


@dataclass(frozen=True)
class ExistingMetadata:
    """Existing generated metadata, if the workspace has been imported before."""

    config: WorkspaceConfig | None
    state: WorkspaceState | None
    is_repaired: bool = False


@dataclass(frozen=True)
class WorkspaceImportResult:
    """Structured result of workspace import workflow."""

    workspace_dir: Path
    config_dir: Path
    config: WorkspaceConfig
    state: WorkspaceState
    affected_paths: list[Path]
    identity: dict[str, str] | None
    already_imported: bool
    dry_run: bool
    repaired: bool = False
    provenance: GitProvenance | None = None
    validation_summary: dict[str, Any] | None = None
    installer_discovered: bool = False
    discovered_stack_status: str | None = None
    recommendations: list[str] = field(default_factory=list)


def resolve_import_paths(*, workspace_dir: Path, config_dir: Path | None) -> tuple[Path, Path]:
    """Resolve the workspace and its existing LZA configuration directory."""
    if config_dir is not None:
        resolved_config_dir = config_dir.expanduser().resolve()
        resolved_workspace_dir = workspace_dir.expanduser().resolve()
    else:
        resolved_workspace_dir = workspace_dir.expanduser().resolve()
        resolved_config_dir = resolved_workspace_dir / ConfigurationConfig().local_path

    if not resolved_workspace_dir.is_dir():
        raise LzaError(f"Workspace directory does not exist: {resolved_workspace_dir}")
    if not resolved_config_dir.is_dir():
        raise LzaError(f"Configuration directory does not exist: {resolved_config_dir}")
    if resolved_config_dir.is_symlink():
        raise LzaError(f"Configuration directory must not be a symlink: {resolved_config_dir}")
    try:
        resolved_config_dir.relative_to(resolved_workspace_dir)
    except ValueError as exc:
        raise LzaError("Configuration directory must be inside the workspace.") from exc
    return resolved_workspace_dir, resolved_config_dir


def load_existing_metadata(
    workspace_dir: Path,
    *,
    force: bool = False,
    repair: bool = False,
) -> ExistingMetadata | None:
    """Load a complete existing metadata pair, or repair partial/corrupted metadata if requested."""
    config_path = workspace_dir / WORKSPACE_CONFIG_FILE
    state_path = workspace_dir / WORKSPACE_STATE_FILE

    if not config_path.exists() and not state_path.exists():
        return None

    if force:
        return None

    config: WorkspaceConfig | None = None
    state: WorkspaceState | None = None
    config_err: Exception | None = None
    state_err: Exception | None = None

    if config_path.exists():
        try:
            config = load_workspace_config(workspace_dir)
        except Exception as exc:
            config_err = exc

    if state_path.exists():
        try:
            state = load_workspace_state(workspace_dir)
        except Exception as exc:
            state_err = exc

    # Both exist and valid
    if config is not None and state is not None:
        return ExistingMetadata(config=config, state=state, is_repaired=False)

    # If repair flag is enabled, reconstruct missing or broken metadata
    if repair:
        repaired_config = config
        repaired_state = state
        if repaired_state is None and repaired_config is not None:
            repaired_state = WorkspaceState.from_config(repaired_config)
        return ExistingMetadata(
            config=repaired_config,
            state=repaired_state,
            is_repaired=True,
        )

    # Neither force nor repair - raise descriptive errors
    if config_path.exists() and not state_path.exists():
        raise LzaError(
            f"Workspace at '{workspace_dir}' has partial metadata; "
            f"'{WORKSPACE_CONFIG_FILE}' was found but '{WORKSPACE_STATE_FILE}' is missing. "
            f"Run `lza import {workspace_dir} --repair` to restore state "
            "or `--force` to recreate metadata."
        )
    if state_path.exists() and not config_path.exists():
        raise LzaError(
            f"Workspace at '{workspace_dir}' has partial metadata; "
            f"'{WORKSPACE_STATE_FILE}' was found but '{WORKSPACE_CONFIG_FILE}' is missing. "
            f"Run `lza import {workspace_dir} --repair` to reconstruct config "
            "or `--force` to recreate metadata."
        )

    err = config_err or state_err
    raise LzaError(
        f"Invalid workspace metadata in {workspace_dir}: {err}. "
        f"Run `lza import {workspace_dir} --repair` to repair it or `--force` to replace it."
    )


def build_import_workspace_config(
    *,
    customer_name: str,
    customer_slug: str,
    aws_profile: str | None = None,
    aws_region: str,
    lza_version: str,
    workspace_dir: Path,
    config_dir: Path,
    existing_config: WorkspaceConfig | None,
    provenance: GitProvenance | None = None,
) -> WorkspaceConfig:
    """Build import metadata, incorporating Git provenance when available."""
    rel_config_path = str(config_dir.relative_to(workspace_dir))

    if provenance and provenance.remote_url:
        template = ConfigurationTemplateConfig(
            source="git",
            repository=provenance.remote_url,
            ref=provenance.branch,
            path=rel_config_path,
        )
        if provenance.repo_type == "codecommit":
            repository = ConfigurationRepositoryConfig(
                type="codecommit",
                repository_name=provenance.repo_name or "lza-config-source",
                branch=provenance.branch,
            )
        else:
            repository = ConfigurationRepositoryConfig(
                type="git",
                repository=provenance.remote_url,
                branch=provenance.branch,
            )
    else:
        template = ConfigurationTemplateConfig(
            source="local",
            path=rel_config_path,
        )
        repository = ConfigurationRepositoryConfig()

    configuration = ConfigurationConfig(
        local_path=rel_config_path,
        template=template,
        repository=repository,
    )
    fields: dict[str, Any] = {
        "customer": CustomerConfig(name=customer_name, slug=customer_slug),
        "aws": AwsConfig(
            profile=aws_profile,
            region=aws_region,
        ),
        "lza": LzaConfig(version=lza_version),
        "configuration": configuration,
    }
    if existing_config is not None:
        return existing_config.model_copy(update=fields)
    return WorkspaceConfig(**fields)


def _metadata_paths(
    workspace_dir: Path,
    existing: ExistingMetadata | None,
    config: WorkspaceConfig,
    state: WorkspaceState,
) -> list[Path]:
    config_path = workspace_dir / WORKSPACE_CONFIG_FILE
    state_path = workspace_dir / WORKSPACE_STATE_FILE

    if (
        existing is None
        or existing.config is None
        or existing.state is None
        or existing.is_repaired
    ):
        return [config_path, state_path]
    return [
        path
        for path, changed in (
            (config_path, existing.config != config),
            (state_path, existing.state != state),
        )
        if changed
    ]


def import_workspace_workflow(
    *,
    workspace_dir: Path,
    config_dir: Path | None = None,
    customer_name: str | None = None,
    aws_auth_type: str = "profile",
    aws_profile: str | None = None,
    aws_region: str = "us-east-1",
    lza_version: str = "v1.15.5",
    dry_run: bool = False,
    force: bool = False,
    repair: bool = False,
    skip_aws_check: bool = False,
) -> WorkspaceImportResult:
    """Execute the pure workspace import workflow and return structured result."""
    resolved_workspace_dir, resolved_config_dir = resolve_import_paths(
        workspace_dir=workspace_dir,
        config_dir=config_dir,
    )
    existing = load_existing_metadata(resolved_workspace_dir, force=force, repair=repair)

    # Validate template files presence
    validate_template(resolved_config_dir)

    if lza_version is not None:
        resolved_version = lza_version
    elif existing and existing.config:
        resolved_version = existing.config.lza.version
    else:
        resolved_version = "v1.15.5"

    # Parse YAML syntax and validate LZA configuration schema
    parsed_yaml = validate_yaml_syntax(resolved_config_dir)
    validate_lza_configuration_schema(
        resolved_config_dir,
        lza_version=resolved_version,
        parsed_files=parsed_yaml,
    )

    # Detect Git repository provenance
    provenance = resolve_git_provenance(resolved_config_dir)
    if provenance is None and resolved_config_dir != resolved_workspace_dir:
        provenance = resolve_git_provenance(resolved_workspace_dir)

    if customer_name:
        resolved_customer_name = customer_name
    elif existing and existing.config:
        resolved_customer_name = existing.config.customer.name
    else:
        resolved_customer_name = resolved_workspace_dir.name

    customer_slug = (
        existing.config.customer.slug
        if existing and existing.config and existing.config.customer.name == resolved_customer_name
        else normalize_customer_slug(resolved_customer_name)
    )

    if aws_auth_type != "profile":
        raise LzaError(f"Invalid AWS auth type: {aws_auth_type}")

    if aws_profile:
        resolved_profile = aws_profile
    elif existing and existing.config:
        resolved_profile = existing.config.aws.profile
    else:
        resolved_profile = f"{customer_slug}-root"

    if aws_region is not None:
        resolved_region = aws_region
    elif existing and existing.config:
        resolved_region = existing.config.aws.region
    else:
        resolved_region = "us-east-1"

    config = build_import_workspace_config(
        customer_name=resolved_customer_name,
        customer_slug=customer_slug,
        aws_profile=resolved_profile,
        aws_region=resolved_region,
        lza_version=resolved_version,
        workspace_dir=resolved_workspace_dir,
        config_dir=resolved_config_dir,
        existing_config=existing.config if existing else None,
        provenance=provenance,
    )

    if existing and existing.state:
        state = existing.state
    else:
        state = WorkspaceState.from_config(config)

    # Track imported state
    state.imported = True
    if state.imported_at is None:
        state.imported_at = datetime.now(UTC)

    # Update operational state with discovered configuration metrics
    if provenance:
        state.config_files_count = provenance.files_count
        if provenance.commit:
            state.config_artifact_sha256 = provenance.commit
        state.config_template_source = provenance.repo_type
    else:
        exclude = PackagingExcludeConfig()
        state.config_files_count = count_config_files(
            resolved_config_dir,
            set(exclude.directories),
            set(exclude.files),
        )
        state.config_template_source = "local"

    identity: dict[str, str] | None = None
    installer_discovered = False
    discovered_stack_status: str | None = None
    recommendations: list[str] = []

    if not skip_aws_check:
        try:
            installer_status = get_installer_status_workflow(
                workspace_dir=resolved_workspace_dir,
                config=config,
                state=state,
                sync_config=not dry_run,
                sync_state=not dry_run,
            )
            identity = installer_status.aws_identity
            config = installer_status.config
            state = installer_status.state or state
            if identity:
                state.management_account_id = identity.get("account")
                state.caller_arn = identity.get("arn")

            if installer_status.cfn_status.exists:
                installer_discovered = True
                discovered_stack_status = (
                    f"{installer_status.cfn_status.stack_name} "
                    f"({installer_status.cfn_status.stack_status})"
                )
            elif installer_status.aws_error:
                recommendations.append(
                    f"AWS connection check failed ({installer_status.aws_error}). "
                    "Verify credentials and run 'lza installer status --sync-config'."
                )
        except Exception as exc:
            recommendations.append(
                f"Live AWS discovery skipped due to error: {exc}. "
                "Run 'lza installer status --sync-config' to sync deployed installer parameters."
            )
    else:
        recommendations.append(
            "Live AWS discovery was skipped (--skip-aws-check). "
            "Run 'lza installer status --sync-config' to synchronize deployed settings."
        )

    # Next-step recommendations
    if installer_discovered:
        if config.configuration.repository.type == "s3" and state.config_downloaded_at is None:
            recommendations.append(
                "Run 'lza config download' to pull the latest remote S3 configuration archive."
            )
        recommendations.append("Run 'lza status' to inspect overall workspace readiness.")
        recommendations.append(
            "Run 'lza config push' to synchronize configuration to the remote destination."
        )
    else:
        if not recommendations:
            recommendations.append(
                "Installer stack was not found in AWS; run 'lza installer plan' "
                "or 'lza installer init' to configure installer deployment."
            )

    paths = _metadata_paths(resolved_workspace_dir, existing, config, state)
    is_repaired = bool(existing and existing.is_repaired)

    if dry_run:
        return WorkspaceImportResult(
            workspace_dir=resolved_workspace_dir,
            config_dir=resolved_config_dir,
            config=config,
            state=state,
            affected_paths=paths,
            identity=identity,
            already_imported=not bool(paths) and not is_repaired,
            dry_run=True,
            repaired=is_repaired,
            provenance=provenance,
            validation_summary={"files_validated": len(parsed_yaml)},
            installer_discovered=installer_discovered,
            discovered_stack_status=discovered_stack_status,
            recommendations=recommendations,
        )

    if not paths and not is_repaired:
        return WorkspaceImportResult(
            workspace_dir=resolved_workspace_dir,
            config_dir=resolved_config_dir,
            config=config,
            state=state,
            affected_paths=[],
            identity=identity,
            already_imported=True,
            dry_run=False,
            repaired=False,
            provenance=provenance,
            validation_summary={"files_validated": len(parsed_yaml)},
            installer_discovered=installer_discovered,
            discovered_stack_status=discovered_stack_status,
            recommendations=recommendations,
        )

    (resolved_workspace_dir / ".lza").mkdir(parents=True, exist_ok=True)
    if resolved_workspace_dir / "lza-workspace.yaml" in paths:
        write_workspace_config(resolved_workspace_dir, config)
    if resolved_workspace_dir / ".lza" / "state.json" in paths:
        write_workspace_state(resolved_workspace_dir, state)

    return WorkspaceImportResult(
        workspace_dir=resolved_workspace_dir,
        config_dir=resolved_config_dir,
        config=config,
        state=state,
        affected_paths=paths,
        identity=identity,
        already_imported=False,
        dry_run=False,
        repaired=is_repaired,
        provenance=provenance,
        validation_summary={"files_validated": len(parsed_yaml)},
        installer_discovered=installer_discovered,
        discovered_stack_status=discovered_stack_status,
        recommendations=recommendations,
    )
