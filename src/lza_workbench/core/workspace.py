"""Customer workspace models and filesystem operations.

Define workspace metadata, persist local state, and manage generated directories.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import typer
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

WORKSPACE_CONFIG_FILE = Path("lza-workspace.yaml")
WORKSPACE_STATE_FILE = Path(".lza") / "state.json"


class WorkspaceModel(BaseModel):
    """Base model for forward-compatible workspace metadata."""

    model_config = ConfigDict(extra="forbid", strict=True)


class CustomerConfig(WorkspaceModel):
    """Customer identity stored in lza-workspace.yaml."""

    name: str
    slug: str


class AwsConfig(WorkspaceModel):
    """AWS defaults stored in lza-workspace.yaml."""

    account_id: str | None = None
    region: str = "us-east-1"
    profile: str | None = None
    role: str | None = None
    access_key: str | None = None
    secret_access_key: str | None = None


class LzaConfig(WorkspaceModel):
    """Landing Zone Accelerator settings stored in lza-workspace.yaml."""

    version: str = "v1.15.5"
    accelerator_prefix: str = "AWSAccelerator"


class InstallerStackTemplateConfig(WorkspaceModel):
    """Source of the CloudFormation template for the installer stack."""

    source: Literal["amazon", "local", "git", "s3"] = "amazon"
    path: str | None = None
    repository: str | None = None
    ref: str | None = None


class InstallerSourceCodeConfig(WorkspaceModel):
    """Source code consumed by the installer pipeline."""

    repository_type: Literal["github", "codecommit", "s3", "codeconnection"] = "github"
    owner: str | None = None
    repository_name: str | None = None
    branch: str | None = None
    bucket: str | None = None
    key: str | None = None
    connection_arn: str | None = None


class InstallerOptionsConfig(WorkspaceModel):
    """CloudFormation parameters for the installer stack."""

    enable_approval_stage: bool = False
    enable_diagnostics_pack: bool = False
    anonymous_data: bool = False
    approval_stage_notify_email_list: list[str] = Field(default_factory=list)
    management_account_email: str | None = None
    audit_account_email: str | None = None
    log_archive_account_email: str | None = None
    control_tower_enabled: bool = True
    use_existing_config_repo: bool = False
    existing_config_repository_name: str | None = None
    existing_config_repository_branch_name: str | None = None
    existing_config_repository_owner: str | None = None
    config_code_connection_arn: str | None = None


class LzaInstaller(WorkspaceModel):
    """Installer defaults persisted for later commands."""

    local_path: str = "aws-accelerator-installer"
    stack_template: InstallerStackTemplateConfig = Field(
        default_factory=InstallerStackTemplateConfig
    )
    source_code: InstallerSourceCodeConfig = Field(default_factory=InstallerSourceCodeConfig)
    options: InstallerOptionsConfig = Field(default_factory=InstallerOptionsConfig)


class ConfigurationTemplateConfig(WorkspaceModel):
    """Source of the starter LZA configuration."""

    source: Literal["packaged", "local", "git"] = "packaged"
    name: str | None = "default"
    path: str | None = None
    repository: str | None = None
    ref: str | None = None


class ConfigurationRepositoryConfig(WorkspaceModel):
    """Destination repository for the LZA configuration pipeline."""

    type: Literal["s3", "codecommit", "git"] = "s3"
    bucket: str | None = None
    prefix: str | None = None
    repository_name: str | None = None
    repository: str | None = None
    branch: str | None = None


class PackagingExcludeConfig(WorkspaceModel):
    """Files omitted from configuration archives."""

    directories: list[str] = Field(default_factory=lambda: [".git", "backup"])
    files: list[str] = Field(default_factory=lambda: [".DS_Store"])


class PackagingConfig(WorkspaceModel):
    """Configuration archive packaging settings."""

    exclude: PackagingExcludeConfig = Field(default_factory=PackagingExcludeConfig)


class ConfigurationConfig(WorkspaceModel):
    """Local LZA configuration and its pipeline destination."""

    local_path: str = "aws-accelerator-config"
    template: ConfigurationTemplateConfig = Field(default_factory=ConfigurationTemplateConfig)
    repository: ConfigurationRepositoryConfig = Field(default_factory=ConfigurationRepositoryConfig)
    packaging: PackagingConfig = Field(default_factory=PackagingConfig)


class PipelineConfig(WorkspaceModel):
    """A named configuration LZA pipeline."""

    name: str = "AWSAccelerator-Pipeline"
    watch: bool = True
    execute: bool = True
    detailed_error_reporting: bool = False
    poll_interval_seconds: int = 30


class PipelineInstaller(WorkspaceModel):
    """A named installer LZA pipeline."""

    name: str = "AWSAccelerator-InstallerStack"


class PipelinesConfig(WorkspaceModel):
    """Named LZA pipelines for configuration and installer."""

    installer: PipelineInstaller = Field(default_factory=PipelineInstaller)
    configuration: PipelineConfig = Field(default_factory=PipelineConfig)


class CliConfig(WorkspaceModel):
    """Default behavior for interactive and pipeline CLI operations."""

    debug: bool = False
    validate_aws_credentials: bool = False
    dry_run: bool = False


class WorkspaceConfig(WorkspaceModel):
    """Validated representation of lza-workspace.yaml."""

    schema_version: int = 2
    customer: CustomerConfig
    aws: AwsConfig
    lza: LzaConfig = Field(default_factory=LzaConfig)
    installer: LzaInstaller = Field(default_factory=LzaInstaller)
    configuration: ConfigurationConfig = Field(default_factory=ConfigurationConfig)
    pipelines: PipelinesConfig = Field(default_factory=PipelinesConfig)
    cli_defaults: CliConfig = Field(default_factory=CliConfig)

    @classmethod
    def create(
        cls,
        *,
        customer_name: str,
        customer_slug: str,
        aws_profile: str,
        aws_region: str,
        lza_config: LzaConfig,
        lza_installer: LzaInstaller | None = None,
    ) -> WorkspaceConfig:
        """Build workspace configuration from resolved command values."""
        return cls(
            customer=CustomerConfig(name=customer_name, slug=customer_slug),
            aws=AwsConfig(profile=aws_profile, region=aws_region),
            lza=lza_config or LzaConfig(),
            installer=lza_installer or LzaInstaller(),
        )


class WorkspaceState(WorkspaceModel):
    """Mutable operational metadata stored in .lza/state.json."""

    model_config = ConfigDict(extra="forbid", strict=False)

    initialized_at: datetime | None = None
    updated_at: datetime | None = None
    management_account_id: str | None = None
    caller_arn: str | None = None
    installer_stack_id: str | None = None
    installer_stack_status: str | None = None
    installer_stack_updated_at: datetime | None = None
    installer_pipeline_execution_id: str | None = None
    config_pipeline_execution_id: str | None = None
    config_uploaded_at: datetime | None = None
    config_downloaded_at: datetime | None = None
    config_artifact_etag: str | None = None
    config_artifact_version_id: str | None = None
    config_artifact_sha256: str | None = None
    config_files_count: int | None = None
    config_last_diff_summary: dict[str, int] | None = None
    installer_downloaded_at: datetime | None = None
    installer_template_version: str | None = None

    @classmethod
    def from_config(cls, config: WorkspaceConfig) -> WorkspaceState:
        """Create empty operational state for a newly initialized workspace."""
        del config
        return cls()


def load_workspace_config(path: Path) -> WorkspaceConfig:
    """Read and validate lza-workspace.yaml."""
    yaml = YAML()
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.load(handle)
        return WorkspaceConfig.model_validate(data)
    except (OSError, YAMLError, ValidationError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid workspace configuration {path}: {exc}") from exc


def write_workspace_config(path: Path, config: WorkspaceConfig) -> None:
    """Write validated workspace configuration as reviewable YAML."""
    yaml = YAML()
    yaml.default_flow_style = False
    with path.open("w", encoding="utf-8") as handle:
        yaml.dump(config.model_dump(mode="json"), handle)


def load_workspace_state(path: Path) -> WorkspaceState:
    """Read and validate mutable operational state."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return WorkspaceState.model_validate(data)
    except (OSError, json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid workspace state {path}: {exc}") from exc


def write_workspace_state(path: Path, state: WorkspaceState) -> None:
    """Write operational state as JSON."""
    path.write_text(
        json.dumps(state.model_dump(mode="json"), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def normalize_customer_slug(customer_name: str) -> str:
    """Normalize a customer name into a filesystem-safe slug."""
    slug = customer_name.strip().lower()
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"[^a-z0-9-]+", "", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    if not slug:
        raise ValueError("Customer name does not produce a valid workspace slug.")
    return slug


def validate_workspace_target(workspace_dir: Path, force: bool) -> None:
    """Prevent accidental overwrite of an existing workspace directory."""
    if not workspace_dir.exists():
        return
    if not workspace_dir.is_dir():
        raise typer.BadParameter(f"Target path exists and is not a directory: {workspace_dir}")
    if force:
        return
    if (workspace_dir / WORKSPACE_CONFIG_FILE).exists():
        raise typer.BadParameter(f"LZA workspace already exists: {workspace_dir}")
    if any(workspace_dir.iterdir()):
        raise typer.BadParameter(f"Target directory is not empty: {workspace_dir}")


def create_workspace(
    *,
    workspace_dir: Path,
    template_config_dir: Path,
    config: WorkspaceConfig,
    state: WorkspaceState,
) -> None:
    """Create or reinitialize generated workspace files."""
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / ".lza" / "logs").mkdir(parents=True, exist_ok=True)
    (workspace_dir / config.installer.local_path).mkdir(parents=True, exist_ok=True)

    _replace_directory(
        source=template_config_dir,
        destination=workspace_dir / config.configuration.local_path,
    )
    write_workspace_config(workspace_dir / WORKSPACE_CONFIG_FILE, config)
    write_workspace_state(workspace_dir / WORKSPACE_STATE_FILE, state)


def planned_write_paths(workspace_dir: Path, config: WorkspaceConfig) -> list[Path]:
    """Return the paths initialization will create or replace."""
    return [
        workspace_dir,
        workspace_dir / WORKSPACE_CONFIG_FILE,
        workspace_dir / config.configuration.local_path,
        workspace_dir / config.installer.local_path,
        workspace_dir / WORKSPACE_STATE_FILE,
        workspace_dir / ".lza" / "logs",
    ]


def _replace_directory(*, source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


@dataclass(frozen=True)
class ConfigDiffResult:
    """Summary of changes between existing and new configuration files."""

    added: list[str]
    modified: list[str]
    removed: list[str]

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.modified or self.removed)


def resolve_workspace_dir(target_dir: Path | None = None) -> Path:
    """Resolve workspace directory containing lza-workspace.yaml starting from cwd or target_dir."""
    current = (target_dir or Path.cwd()).expanduser().resolve()
    for directory in [current, *current.parents]:
        if (directory / WORKSPACE_CONFIG_FILE).is_file():
            return directory
    raise typer.BadParameter(
        f"Command must be run inside an LZA workspace directory (missing {WORKSPACE_CONFIG_FILE})."
    )


def resolve_init_workspace_dir(
    *,
    customer_name: str,
    workspace_dir: Path | None,
    interactive: bool,
) -> Path:
    """Resolve the target workspace directory for init or import operations."""
    default = Path.cwd() / normalize_customer_slug(customer_name)
    if workspace_dir is not None:
        return workspace_dir.expanduser().resolve()
    if interactive:
        return (
            Path(typer.prompt("Workspace directory", default=str(default))).expanduser().resolve()
        )
    return default.resolve()


def is_path_excluded(
    rel_path: Path,
    exclude_dirs: set[str],
    exclude_files: set[str] | None = None,
) -> bool:
    """Check if a relative file path matches excluded directory or file rules."""
    if any(part in exclude_dirs for part in rel_path.parts[:-1]):
        return True
    if exclude_files and rel_path.name in exclude_files:
        return True
    return False


def count_config_files(config_dir: Path, exclude_dirs: set[str]) -> int:
    """Count configuration files in directory using an explicit loop."""
    if not config_dir.is_dir():
        return 0

    total_files = 0
    for path in config_dir.rglob("*"):
        if not path.is_file():
            continue
        rel_path = path.relative_to(config_dir)
        if not is_path_excluded(rel_path, exclude_dirs):
            total_files += 1

    return total_files


def build_installer_cfn_parameters(config: WorkspaceConfig) -> dict[str, str]:
    """Map workspace configuration into CloudFormation parameter key-value pairs."""
    source_code = config.installer.source_code
    options = config.installer.options
    repo_config = config.configuration.repository

    branch = (source_code.branch or "").strip()
    if not branch:
        lza_ver = (config.lza.version or "").strip()
        if lza_ver == "latest":
            branch = "main"
        elif not lza_ver.startswith("release/"):
            norm = lza_ver if lza_ver.startswith("v") else f"v{lza_ver}"
            branch = f"release/{norm}"
        else:
            branch = lza_ver

    notify_emails = ",".join(options.approval_stage_notify_email_list)

    return {
        "RepositorySource": source_code.repository_type or "github",
        "RepositoryOwner": source_code.owner or "awslabs",
        "RepositoryName": source_code.repository_name or "landing-zone-accelerator-on-aws",
        "RepositoryBranchName": branch,
        "EnableApprovalStage": "Yes" if options.enable_approval_stage else "No",
        "ApprovalStageNotifyEmailList": notify_emails,
        "ManagementAccountEmail": options.management_account_email or "",
        "LogArchiveAccountEmail": options.log_archive_account_email or "",
        "AuditAccountEmail": options.audit_account_email or "",
        "ControlTowerEnabled": "Yes" if options.control_tower_enabled else "No",
        "AcceleratorPrefix": config.lza.accelerator_prefix or "AWSAccelerator",
        "ConfigurationRepositoryLocation": repo_config.type or "s3",
        "UseExistingConfigRepo": "Yes" if options.use_existing_config_repo else "No",
        "ConfigCodeConnectionArn": (
            options.config_code_connection_arn or source_code.connection_arn or ""
        ),
        "ExistingConfigRepositoryOwner": options.existing_config_repository_owner or "",
        "ExistingConfigRepositoryName": (
            options.existing_config_repository_name or repo_config.repository_name or ""
        ),
        "ExistingConfigRepositoryBranchName": (
            options.existing_config_repository_branch_name or repo_config.branch or ""
        ),
        "EnableDiagnosticsPack": "Yes" if options.enable_diagnostics_pack else "No",
    }

