"""Customer workspace models and filesystem operations.

Define workspace metadata, persist local state, and manage generated directories.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import typer
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

INSTALLER_STACK_NAME = "AWSAccelerator-InstallerStack"
WORKSPACE_CONFIG_FILE = Path("lza-workspace.yaml")
WORKSPACE_STATE_FILE = Path(".lza") / "state.json"


class WorkspaceModel(BaseModel):
    """Base model for forward-compatible workspace metadata."""

    model_config = ConfigDict(extra="allow", strict=True)


class CustomerConfig(WorkspaceModel):
    """Customer identity stored in lza-workspace.yaml."""

    name: str
    slug: str


class AwsConfig(WorkspaceModel):
    """AWS defaults stored in lza-workspace.yaml."""

    profile: str
    region: str


class LzaConfig(WorkspaceModel):
    """Landing Zone Accelerator settings stored in lza-workspace.yaml."""

    version: str
    accelerator_prefix: str = "AWSAccelerator"
    config_repository_location: str = "s3"
    template_source_type: str
    template_source: str


class InstallerSettings(WorkspaceModel):
    """Installer defaults persisted for later commands."""

    control_tower_enabled: bool = True
    enable_approval_stage: bool = True
    enable_diagnostics_pack: bool = True
    anonymous_data: bool = False


class WorkspaceConfig(WorkspaceModel):
    """Validated representation of lza-workspace.yaml."""

    customer: CustomerConfig
    aws: AwsConfig
    lza: LzaConfig
    installer: InstallerSettings = Field(default_factory=InstallerSettings)

    @classmethod
    def create(
        cls,
        *,
        customer_name: str,
        customer_slug: str,
        aws_profile: str,
        aws_region: str,
        lza_version: str,
        template_source: str,
        template_source_type: str,
        installer: InstallerSettings | None = None,
    ) -> WorkspaceConfig:
        """Build workspace configuration from resolved command values."""
        return cls(
            customer=CustomerConfig(name=customer_name, slug=customer_slug),
            aws=AwsConfig(profile=aws_profile, region=aws_region),
            lza=LzaConfig(
                version=lza_version,
                template_source=template_source,
                template_source_type=template_source_type,
            ),
            installer=installer or InstallerSettings(),
        )


class WorkspaceState(WorkspaceModel):
    """Mutable operational metadata stored in .lza/state.json."""

    customer: str
    lza_version: str
    aws_profile: str
    aws_region: str
    installer_stack_name: str = INSTALLER_STACK_NAME
    config_location: str
    last_pipeline_execution_id: str | None = None

    @classmethod
    def from_config(cls, config: WorkspaceConfig) -> WorkspaceState:
        """Initialize operational state from durable workspace configuration."""
        return cls(
            customer=config.customer.slug,
            lza_version=config.lza.version,
            aws_profile=config.aws.profile,
            aws_region=config.aws.region,
            config_location=config.lza.config_repository_location,
        )


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
    (workspace_dir / "aws-accelerator-installer").mkdir(parents=True, exist_ok=True)

    _replace_directory(
        source=template_config_dir,
        destination=workspace_dir / "aws-accelerator-config",
    )
    write_workspace_config(workspace_dir / WORKSPACE_CONFIG_FILE, config)
    write_workspace_state(workspace_dir / WORKSPACE_STATE_FILE, state)


def planned_write_paths(workspace_dir: Path) -> list[Path]:
    return [
        workspace_dir,
        workspace_dir / WORKSPACE_CONFIG_FILE,
        workspace_dir / "aws-accelerator-config",
        workspace_dir / "aws-accelerator-installer",
        workspace_dir / WORKSPACE_STATE_FILE,
        workspace_dir / ".lza" / "logs",
    ]


def _replace_directory(*, source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
