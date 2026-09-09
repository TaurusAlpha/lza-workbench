"""Workflow for importing and adopting an existing LZA workspace."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lza_workbench.aws.cloudformation import (
    get_cloudformation_stack_status,
    get_cloudformation_stack_template,
)
from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.aws.secrets_manager import inspect_secret_details
from lza_workbench.configuration.archive import count_config_files
from lza_workbench.configuration.git import (
    GitProvenance,
    resolve_git_provenance,
)
from lza_workbench.configuration.repository import get_canonical_config_s3_bucket
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
from lza_workbench.installer.deployed_version import resolve_deployed_installer_version
from lza_workbench.installer.schema import LzaInstaller
from lza_workbench.installer.source import validate_github_repository_access
from lza_workbench.installer.sync import (
    apply_installer_config_sync,
    apply_installer_state_sync,
    prepare_installer_template_sync,
    write_installer_template,
)
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
class ImportWorkspaceDiscovery:
    """Validated import paths and existing metadata used to collect command inputs."""

    workspace_dir: Path
    config_dir: Path
    existing: ExistingMetadata | None


@dataclass(frozen=True)
class ImportWorkspaceRequest:
    """Inputs for preparing an existing workspace for import."""

    workspace_dir: Path
    config_dir: Path | None = None
    customer_name: str | None = None
    aws_auth_type: str = "profile"
    aws_profile: str | None = None
    aws_region: str = "us-east-1"
    lza_version: str = "v1.15.5"
    installer_stack_name: str | None = None
    dry_run: bool = False
    force: bool = False
    repair: bool = False
    skip_aws_check: bool = False
    prime_credentials: bool = False
    discovery: ImportWorkspaceDiscovery | None = None


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


@dataclass(frozen=True)
class ImportWorkspacePreparation:
    """Read-only import discovery, desired metadata, and intended file changes."""

    result: WorkspaceImportResult
    installer_template_path: Path | None = None
    installer_template_body: str | None = None


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


def _load_existing_config(
    workspace_dir: Path,
    *,
    config_path: Path,
) -> tuple[WorkspaceConfig | None, Exception | None]:
    if not config_path.exists():
        return None, None
    try:
        return load_workspace_config(workspace_dir), None
    except Exception as exc:
        return None, exc


def _load_existing_state(
    workspace_dir: Path,
    *,
    state_path: Path,
) -> tuple[WorkspaceState | None, Exception | None]:
    if not state_path.exists():
        return None, None
    try:
        return load_workspace_state(workspace_dir), None
    except Exception as exc:
        return None, exc


def _repair_existing_metadata(
    config: WorkspaceConfig | None,
    state: WorkspaceState | None,
) -> ExistingMetadata:
    if state is None and config is not None:
        state = WorkspaceState.from_config(config)
    return ExistingMetadata(config=config, state=state, is_repaired=True)


def _raise_invalid_metadata_error(
    *,
    workspace_dir: Path,
    config_path: Path,
    state_path: Path,
    config_error: Exception | None,
    state_error: Exception | None,
) -> None:
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

    err = config_error or state_error
    raise LzaError(
        f"Invalid workspace metadata in {workspace_dir}: {err}. "
        f"Run `lza import {workspace_dir} --repair` to repair it or `--force` to replace it."
    )


def load_existing_metadata(
    workspace_dir: Path,
    *,
    force: bool = False,
    repair: bool = False,
) -> ExistingMetadata | None:
    """Load a complete existing metadata pair, or repair partial/corrupted metadata if requested."""
    config_path = workspace_dir / WORKSPACE_CONFIG_FILE
    state_path = workspace_dir / WORKSPACE_STATE_FILE
    if force or (not config_path.exists() and not state_path.exists()):
        return None

    config, config_error = _load_existing_config(workspace_dir, config_path=config_path)
    state, state_error = _load_existing_state(workspace_dir, state_path=state_path)
    if config is not None and state is not None:
        return ExistingMetadata(config=config, state=state)
    if repair:
        return _repair_existing_metadata(config, state)
    _raise_invalid_metadata_error(
        workspace_dir=workspace_dir,
        config_path=config_path,
        state_path=state_path,
        config_error=config_error,
        state_error=state_error,
    )


def discover_import_workspace(
    *,
    workspace_dir: Path,
    config_dir: Path | None,
    force: bool = False,
    repair: bool = False,
) -> ImportWorkspaceDiscovery:
    """Resolve and validate import inputs before an interface prompts for overrides."""
    resolved_workspace_dir, resolved_config_dir = resolve_import_paths(
        workspace_dir=workspace_dir,
        config_dir=config_dir,
    )
    return ImportWorkspaceDiscovery(
        workspace_dir=resolved_workspace_dir,
        config_dir=resolved_config_dir,
        existing=load_existing_metadata(resolved_workspace_dir, force=force, repair=repair),
    )


def _build_import_configuration_source(
    *,
    provenance: GitProvenance | None,
    relative_config_path: str,
) -> tuple[ConfigurationTemplateConfig, ConfigurationRepositoryConfig]:
    if provenance and provenance.remote_url:
        template = ConfigurationTemplateConfig(
            source="git",
            repository=provenance.remote_url,
            ref=provenance.branch,
            path=relative_config_path,
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
            path=relative_config_path,
        )
        repository = ConfigurationRepositoryConfig()
    return template, repository


def _resolve_import_configuration(
    *,
    existing_config: WorkspaceConfig | None,
    relative_config_path: str,
    template: ConfigurationTemplateConfig,
    repository: ConfigurationRepositoryConfig,
) -> ConfigurationConfig:
    if existing_config is not None:
        return existing_config.configuration.model_copy(update={"local_path": relative_config_path})
    return ConfigurationConfig(
        local_path=relative_config_path,
        template=template,
        repository=repository,
    )


def _resolve_import_installer(
    *,
    existing_config: WorkspaceConfig | None,
    installer_stack_name: str | None,
) -> LzaInstaller:
    resolved_stack_name = (
        installer_stack_name
        or (existing_config.installer.stack_name if existing_config else None)
        or "AWSAccelerator-InstallerStack"
    )
    if existing_config:
        return existing_config.installer.model_copy(update={"stack_name": resolved_stack_name})
    return LzaInstaller(stack_name=resolved_stack_name)


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
    installer_stack_name: str | None = None,
    prime_credentials: bool = False,
) -> WorkspaceConfig:
    """Build import metadata, incorporating Git provenance when available."""
    relative_config_path = str(config_dir.relative_to(workspace_dir))
    template, repository = _build_import_configuration_source(
        provenance=provenance,
        relative_config_path=relative_config_path,
    )

    if repository.type == "s3" and not repository.bucket and aws_region:
        account_id = existing_config.aws.account_id if existing_config else None
        if account_id:
            repository.bucket = get_canonical_config_s3_bucket(account_id, aws_region)

    configuration = _resolve_import_configuration(
        existing_config=existing_config,
        relative_config_path=relative_config_path,
        template=template,
        repository=repository,
    )
    installer = _resolve_import_installer(
        existing_config=existing_config,
        installer_stack_name=installer_stack_name,
    )
    fields: dict[str, Any] = {
        "customer": CustomerConfig(name=customer_name, slug=customer_slug),
        "aws": AwsConfig(
            profile=aws_profile,
            region=aws_region,
            prime_credentials=prime_credentials,
        ),
        "lza": LzaConfig(version=lza_version),
        "configuration": configuration,
        "installer": installer,
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


def _resolve_lza_version(request: ImportWorkspaceRequest, existing: ExistingMetadata | None) -> str:
    if request.lza_version is not None:
        return request.lza_version
    if existing and existing.config:
        return existing.config.lza.version
    return "v1.15.5"


def _resolve_import_parameters(
    request: ImportWorkspaceRequest,
    existing: ExistingMetadata | None,
    resolved_workspace_dir: Path,
) -> tuple[str, str, str | None, str]:
    if request.customer_name:
        customer_name = request.customer_name
    elif existing and existing.config:
        customer_name = existing.config.customer.name
    else:
        customer_name = resolved_workspace_dir.name

    customer_slug = (
        existing.config.customer.slug
        if existing and existing.config and existing.config.customer.name == customer_name
        else normalize_customer_slug(customer_name)
    )

    if request.aws_auth_type != "profile":
        raise LzaError(f"Invalid AWS auth type: {request.aws_auth_type}")

    if request.aws_profile:
        aws_profile = request.aws_profile
    elif existing and existing.config:
        aws_profile = existing.config.aws.profile
    else:
        aws_profile = f"{customer_slug}-root"

    if request.aws_region is not None:
        aws_region = request.aws_region
    elif existing and existing.config:
        aws_region = existing.config.aws.region
    else:
        aws_region = "us-east-1"

    return customer_name, customer_slug, aws_profile, aws_region


def _initialize_import_state(
    config: WorkspaceConfig,
    existing: ExistingMetadata | None,
    provenance: GitProvenance | None,
    resolved_config_dir: Path,
) -> WorkspaceState:
    if existing and existing.state:
        state = existing.state.model_copy(deep=True)
    else:
        state = WorkspaceState.from_config(config)

    state.imported = True
    if state.imported_at is None:
        state.imported_at = datetime.now(UTC)

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

    return state


def _check_github_installer_secret(
    aws_ctx: Any,
    config: WorkspaceConfig,
    recommendations: list[str],
) -> None:
    try:
        sm_client = aws_ctx.factory.get_client("secretsmanager")
        secret_name = config.installer.source_code.github_secret_name or "accelerator/github-token"
        secret_details = inspect_secret_details(client=sm_client, secret_name=secret_name)
        if not secret_details.exists:
            recommendations.append(
                "GitHub installer source detected, but Secrets Manager "
                f"secret '{secret_name}' was not found. Create this secret "
                "containing a valid GitHub token before deployment."
            )
        elif secret_details.value:
            gh_res = validate_github_repository_access(
                owner=config.installer.source_code.owner or "awslabs",
                repository_name=config.installer.source_code.repository_name
                or "landing-zone-accelerator-on-aws",
                branch=config.installer.source_code.branch,
                token=secret_details.value,
            )
            if not gh_res["accessible"]:
                recommendations.append(f"GitHub repository check returned: {gh_res['error']}")
    except Exception as gh_exc:
        recommendations.append(f"GitHub token validation check skipped: {gh_exc}")


def _inspect_live_installer(
    aws_ctx: Any,
    workspace_dir: Path,
    config: WorkspaceConfig,
    state: WorkspaceState,
    recommendations: list[str],
) -> tuple[WorkspaceConfig, WorkspaceState, bool, str | None, Path | None, str | None]:
    stack_name = config.installer.stack_name or "AWSAccelerator-InstallerStack"
    cfn_client = aws_ctx.factory.get_client("cloudformation")
    cfn_status = get_cloudformation_stack_status(client=cfn_client, stack_name=stack_name)

    if not cfn_status.exists:
        return config, state, False, None, None, None

    installer_discovered = True
    discovered_stack_status = f"{cfn_status.stack_name} ({cfn_status.stack_status})"
    ssm_client = aws_ctx.factory.get_client("ssm")
    deployed_template = get_cloudformation_stack_template(client=cfn_client, stack_name=stack_name)
    if deployed_template is None:
        recommendations.append(
            "Live installer template could not be retrieved. Ensure the AWS identity "
            "has cloudformation:GetTemplate, then run 'lza installer import'."
        )
    deployed_version = resolve_deployed_installer_version(
        cfn_client=cfn_client,
        ssm_client=ssm_client,
        stack_name=stack_name,
        accelerator_prefix=(
            cfn_status.deployed_parameters.get("AcceleratorPrefix") or config.lza.accelerator_prefix
        ),
    )
    installer_template_path: Path | None = None
    installer_template_body: str | None = None
    if deployed_template is not None:
        installer_template_path = prepare_installer_template_sync(
            workspace_dir=workspace_dir,
            config=config,
            state=state,
            template_body=deployed_template,
        )
        installer_template_body = deployed_template
    config = apply_installer_config_sync(
        config=config,
        cfn_status=cfn_status,
        deployed_version=deployed_version,
    )
    state = apply_installer_state_sync(
        state=state,
        cfn_status=cfn_status,
        deployed_version=deployed_version,
    )
    if config.installer.source_code.repository_type == "github":
        _check_github_installer_secret(aws_ctx, config, recommendations)

    return (
        config,
        state,
        installer_discovered,
        discovered_stack_status,
        installer_template_path,
        installer_template_body,
    )


def _discover_live_aws(
    request: ImportWorkspaceRequest,
    workspace_dir: Path,
    config: WorkspaceConfig,
    state: WorkspaceState,
) -> tuple[
    WorkspaceConfig,
    WorkspaceState,
    dict[str, str] | None,
    bool,
    str | None,
    list[str],
    Path | None,
    str | None,
]:
    recommendations: list[str] = []
    if request.skip_aws_check:
        recommendations.append(
            "Live AWS discovery was skipped (--skip-aws-check). "
            "Run 'lza installer import' to synchronize deployed settings."
        )
        return config, state, None, False, None, recommendations, None, None

    identity: dict[str, str] | None = None
    installer_discovered = False
    discovered_stack_status: str | None = None
    installer_template_path: Path | None = None
    installer_template_body: str | None = None

    try:
        aws_ctx = resolve_aws_execution_context(
            profile=config.aws.profile,
            region=config.aws.region,
            role_arn=config.aws.role_arn,
            expected_account_id=config.aws.account_id,
            prime_credentials=config.aws.prime_credentials,
        )
        identity = aws_ctx.identity
        if identity:
            state.management_account_id = identity.get("account")
            state.caller_arn = identity.get("arn")
            (
                config,
                state,
                installer_discovered,
                discovered_stack_status,
                installer_template_path,
                installer_template_body,
            ) = _inspect_live_installer(aws_ctx, workspace_dir, config, state, recommendations)
        elif aws_ctx.error:
            recommendations.append(
                f"AWS connection check failed ({aws_ctx.error}). "
                "Verify credentials and run 'lza installer import'."
            )
    except Exception as exc:
        recommendations.append(
            f"Live AWS discovery skipped due to error: {exc}. "
            "Run 'lza installer import' to sync deployed installer parameters."
        )

    return (
        config,
        state,
        identity,
        installer_discovered,
        discovered_stack_status,
        recommendations,
        installer_template_path,
        installer_template_body,
    )


def _build_import_recommendations(
    installer_discovered: bool,
    config: WorkspaceConfig,
    state: WorkspaceState,
    recommendations: list[str],
) -> None:
    if installer_discovered:
        if config.configuration.repository.type == "s3" and state.config_downloaded_at is None:
            recommendations.append(
                "Run 'lza config download' to pull the latest remote S3 configuration archive."
            )
        recommendations.append("Run 'lza status' to inspect overall workspace readiness.")
        recommendations.append(
            "Run 'lza config push' to synchronize configuration to the remote destination."
        )
    elif not recommendations:
        recommendations.append(
            "Installer stack was not found in AWS; run 'lza installer plan' "
            "or 'lza installer init' to configure installer deployment."
        )


def _collect_import_paths(
    workspace_dir: Path,
    existing: ExistingMetadata | None,
    config: WorkspaceConfig,
    state: WorkspaceState,
    installer_template_path: Path | None,
    installer_template_body: str | None,
) -> list[Path]:
    paths = _metadata_paths(workspace_dir, existing, config, state)
    if (
        installer_template_path is not None
        and installer_template_body is not None
        and (
            not installer_template_path.is_file()
            or installer_template_path.read_text(encoding="utf-8") != installer_template_body
        )
    ):
        paths.append(installer_template_path)
    return paths


def prepare_workspace_import(request: ImportWorkspaceRequest) -> ImportWorkspacePreparation:
    """Discover an existing workspace and derive import metadata without writing files."""
    discovery = request.discovery
    if discovery is None:
        discovery = discover_import_workspace(
            workspace_dir=request.workspace_dir,
            config_dir=request.config_dir,
            force=request.force,
            repair=request.repair,
        )
    resolved_workspace_dir = discovery.workspace_dir
    resolved_config_dir = discovery.config_dir
    existing = discovery.existing

    # Validate template files presence
    validate_template(resolved_config_dir)

    resolved_version = _resolve_lza_version(request, existing)

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

    customer_name, customer_slug, aws_profile, aws_region = _resolve_import_parameters(
        request, existing, resolved_workspace_dir
    )

    config = build_import_workspace_config(
        customer_name=customer_name,
        customer_slug=customer_slug,
        aws_profile=aws_profile,
        aws_region=aws_region,
        lza_version=resolved_version,
        workspace_dir=resolved_workspace_dir,
        config_dir=resolved_config_dir,
        existing_config=existing.config if existing else None,
        provenance=provenance,
        installer_stack_name=request.installer_stack_name,
        prime_credentials=request.prime_credentials,
    )
    if existing and existing.config and config.configuration != existing.config.configuration:
        raise LzaError(
            "Import would rewrite existing configuration metadata. "
            "Re-run with --force to intentionally replace workspace metadata."
        )

    state = _initialize_import_state(config, existing, provenance, resolved_config_dir)

    (
        config,
        state,
        identity,
        installer_discovered,
        discovered_stack_status,
        recommendations,
        installer_template_path,
        installer_template_body,
    ) = _discover_live_aws(request, resolved_workspace_dir, config, state)

    _build_import_recommendations(installer_discovered, config, state, recommendations)

    paths = _collect_import_paths(
        resolved_workspace_dir,
        existing,
        config,
        state,
        installer_template_path,
        installer_template_body,
    )
    is_repaired = bool(existing and existing.is_repaired)

    result = WorkspaceImportResult(
        workspace_dir=resolved_workspace_dir,
        config_dir=resolved_config_dir,
        config=config,
        state=state,
        affected_paths=paths,
        identity=identity,
        already_imported=not bool(paths) and not is_repaired,
        dry_run=request.dry_run,
        repaired=is_repaired,
        provenance=provenance,
        validation_summary={"files_validated": len(parsed_yaml)},
        installer_discovered=installer_discovered,
        discovered_stack_status=discovered_stack_status,
        recommendations=recommendations,
    )
    return ImportWorkspacePreparation(
        result=result,
        installer_template_path=installer_template_path,
        installer_template_body=installer_template_body,
    )


def apply_workspace_import(preparation: ImportWorkspacePreparation) -> WorkspaceImportResult:
    """Persist a prepared import without repeating discovery or validation."""
    result = preparation.result
    if result.dry_run or result.already_imported:
        return result

    workspace_dir = result.workspace_dir
    paths = result.affected_paths
    (workspace_dir / ".lza").mkdir(parents=True, exist_ok=True)
    if (
        preparation.installer_template_path in paths
        and preparation.installer_template_body is not None
    ):
        write_installer_template(
            template_path=preparation.installer_template_path,
            template_body=preparation.installer_template_body,
        )
    if workspace_dir / WORKSPACE_CONFIG_FILE in paths:
        write_workspace_config(workspace_dir, result.config)
    if workspace_dir / WORKSPACE_STATE_FILE in paths:
        write_workspace_state(workspace_dir, result.state)
    return result


def import_workspace_workflow(
    *,
    workspace_dir: Path,
    config_dir: Path | None = None,
    customer_name: str | None = None,
    aws_auth_type: str = "profile",
    aws_profile: str | None = None,
    aws_region: str = "us-east-1",
    lza_version: str = "v1.15.5",
    installer_stack_name: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    repair: bool = False,
    skip_aws_check: bool = False,
    prime_credentials: bool = False,
    discovery: ImportWorkspaceDiscovery | None = None,
) -> WorkspaceImportResult:
    """Convenience composition of workspace import preparation and application."""
    return apply_workspace_import(
        prepare_workspace_import(
            ImportWorkspaceRequest(
                workspace_dir=workspace_dir,
                config_dir=config_dir,
                customer_name=customer_name,
                aws_auth_type=aws_auth_type,
                aws_profile=aws_profile,
                aws_region=aws_region,
                lza_version=lza_version,
                installer_stack_name=installer_stack_name,
                dry_run=dry_run,
                force=force,
                repair=repair,
                skip_aws_check=skip_aws_check,
                prime_credentials=prime_credentials,
                discovery=discovery,
            )
        )
    )


__all__ = [
    "ExistingMetadata",
    "ImportWorkspaceDiscovery",
    "ImportWorkspacePreparation",
    "ImportWorkspaceRequest",
    "WorkspaceImportResult",
    "apply_workspace_import",
    "build_import_workspace_config",
    "discover_import_workspace",
    "import_workspace_workflow",
    "load_existing_metadata",
    "prepare_workspace_import",
    "resolve_import_paths",
]
