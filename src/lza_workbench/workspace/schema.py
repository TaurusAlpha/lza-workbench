"""Top-level workspace schema models for LZA Workbench."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lza_workbench.configuration.runtime import ConfigurationRuntimeState
from lza_workbench.configuration.schema import ConfigurationConfig
from lza_workbench.errors import LzaError
from lza_workbench.installer.runtime import InstallerRuntimeState
from lza_workbench.installer.schema import LzaInstaller, PipelineInstaller
from lza_workbench.pipeline.runtime import PipelinesRuntimeState
from lza_workbench.workspace.uninstall.state import UninstallRuntimeState


class WorkspaceModel(BaseModel):
    """Shared strict base model for workspace documents."""

    model_config = ConfigDict(extra="forbid", strict=False)


class CustomerConfig(WorkspaceModel):
    name: str
    slug: str


class AwsConfig(WorkspaceModel):
    account_id: str | None = None
    region: str = "us-east-1"
    profile: str | None = None
    role_arn: str | None = None
    prime_credentials: bool = False

    @model_validator(mode="after")
    def require_profile(self) -> AwsConfig:
        has_profile = bool(self.profile and self.profile.strip())
        has_role_arn = bool(self.role_arn and self.role_arn.strip())
        if not has_profile and not has_role_arn:
            raise LzaError("AWS configuration requires a profile or role_arn.")
        return self


class LzaConfig(WorkspaceModel):
    version: str = "v1.15.5"
    accelerator_prefix: str = Field(
        default="AWSAccelerator",
        max_length=15,
        pattern=r"^[A-Za-z0-9-]+$",
        description="The prefix value for accelerator deployed resources.",
    )


class PipelineConfig(WorkspaceModel):
    """A named configuration LZA pipeline."""

    name: str = "AWSAccelerator-Pipeline"
    watch: bool = True
    execute: bool = True
    detailed_error_reporting: bool = False
    poll_interval_seconds: int = 30


class PipelinesConfig(WorkspaceModel):
    """Named LZA pipelines for configuration and installer."""

    installer: PipelineInstaller = Field(default_factory=PipelineInstaller)
    configuration: PipelineConfig = Field(default_factory=PipelineConfig)


class CliConfig(WorkspaceModel):
    debug: bool = False
    validate_aws_credentials: bool = False
    dry_run: bool = False


class WorkspaceConfig(WorkspaceModel):
    schema_version: int = 2
    customer: CustomerConfig
    aws: AwsConfig
    assets_bucket: str | None = None
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
        aws_profile: str | None = None,
        aws_role_arn: str | None = None,
        aws_region: str,
        lza_version: str,
        lza_config: LzaConfig | None = None,
        lza_installer: LzaInstaller | None = None,
    ) -> WorkspaceConfig:
        """Build workspace configuration from resolved command values."""
        return cls(
            customer=CustomerConfig(name=customer_name, slug=customer_slug),
            aws=AwsConfig(profile=aws_profile, role_arn=aws_role_arn, region=aws_region),
            lza=lza_config or LzaConfig(version=lza_version),
            installer=lza_installer or LzaInstaller(),
        )


class WorkspaceState(WorkspaceModel):
    initialized_at: datetime | None = None
    updated_at: datetime | None = None
    management_account_id: str | None = None
    caller_arn: str | None = None
    imported: bool | None = None
    imported_at: datetime | None = None
    installer: InstallerRuntimeState = Field(default_factory=InstallerRuntimeState)
    configuration: ConfigurationRuntimeState = Field(default_factory=ConfigurationRuntimeState)
    pipelines: PipelinesRuntimeState = Field(default_factory=PipelinesRuntimeState)
    uninstall: UninstallRuntimeState = Field(default_factory=UninstallRuntimeState)

    @classmethod
    def from_config(cls, config: WorkspaceConfig) -> WorkspaceState:
        """Create empty operational state for a newly initialized workspace."""
        del config
        return cls()
