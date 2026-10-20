"""Top-level workspace schema models for LZA Workbench."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from lza_workbench.configuration.schema import (
    ConfigurationConfig,
    ConfigurationRepositoryConfig,
)
from lza_workbench.configuration.state import ConfigurationState
from lza_workbench.installer.schema import LzaInstaller, PipelineInstaller
from lza_workbench.installer.state import InstallerState
from lza_workbench.pipeline.state import PipelinesState
from lza_workbench.workspace.uninstall.state import UninstallState


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


class LzaConfig(WorkspaceModel):
    version: str = "v1.15.5"
    accelerator_prefix: str = Field(
        default="AWSAccelerator",
        max_length=15,
        pattern=r"^[A-Za-z0-9-]+$",
        description="The prefix value for accelerator deployed resources.",
    )


class CustomerEnvironmentTarget(WorkspaceModel):
    """Customer and AWS resource targets usable without local paths or engineer credentials."""

    customer: CustomerConfig
    account_id: str | None = None
    region: str = "us-east-1"
    lza: LzaConfig = Field(default_factory=LzaConfig)
    assets_bucket: str | None = None
    installer_stack_name: str = "AWSAccelerator-InstallerStack"
    installer_pipeline_name: str = "AWSAccelerator-Installer"
    configuration_pipeline_name: str = "AWSAccelerator-Pipeline"
    configuration_repository: ConfigurationRepositoryConfig = Field(
        default_factory=ConfigurationRepositoryConfig
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
    aws: AwsConfig = Field(default_factory=AwsConfig)
    assets_bucket: str | None = None
    lza: LzaConfig = Field(default_factory=LzaConfig)
    installer: LzaInstaller = Field(default_factory=LzaInstaller)
    configuration: ConfigurationConfig = Field(default_factory=ConfigurationConfig)
    pipelines: PipelinesConfig = Field(default_factory=PipelinesConfig)
    cli_defaults: CliConfig = Field(default_factory=CliConfig)

    @property
    def environment_target(self) -> CustomerEnvironmentTarget:
        prefix = self.lza.accelerator_prefix or "AWSAccelerator"
        return CustomerEnvironmentTarget(
            customer=self.customer,
            account_id=self.aws.account_id,
            region=self.aws.region,
            lza=self.lza,
            assets_bucket=self.assets_bucket,
            installer_stack_name=self.installer.stack_name or f"{prefix}-InstallerStack",
            installer_pipeline_name=self.pipelines.installer.name or f"{prefix}-Installer",
            configuration_pipeline_name=self.pipelines.configuration.name or f"{prefix}-Pipeline",
            configuration_repository=self.configuration.repository,
        )

    @classmethod
    def create(
        cls,
        *,
        customer_name: str,
        customer_slug: str,
        aws_profile: str | None = None,
        aws_role_arn: str | None = None,
        aws_region: str = "us-east-1",
        aws_account_id: str | None = None,
        lza_version: str = "v1.15.5",
        lza_config: LzaConfig | None = None,
        lza_installer: LzaInstaller | None = None,
    ) -> WorkspaceConfig:
        """Build workspace configuration from resolved command values."""
        return cls(
            customer=CustomerConfig(name=customer_name, slug=customer_slug),
            aws=AwsConfig(
                account_id=aws_account_id,
                profile=aws_profile,
                role_arn=aws_role_arn,
                region=aws_region,
            ),
            lza=lza_config or LzaConfig(version=lza_version),
            installer=lza_installer or LzaInstaller(),
        )


class WorkspaceMetadataState(WorkspaceModel):
    """Local workspace lifecycle and provenance metadata."""

    initialized_at: datetime | None = None
    imported: bool = False
    imported_at: datetime | None = None
    updated_at: datetime | None = None


class WorkspaceState(WorkspaceModel):
    """Persisted local operational state for an LZA workspace (.lza/state.json)."""

    schema_version: int = 2
    workspace: WorkspaceMetadataState = Field(default_factory=WorkspaceMetadataState)
    installer: InstallerState = Field(default_factory=InstallerState)
    configuration: ConfigurationState = Field(default_factory=ConfigurationState)
    pipelines: PipelinesState = Field(default_factory=PipelinesState)
    uninstall: UninstallState = Field(default_factory=UninstallState)

    @property
    def observed_account_id(self) -> str | None:
        """Return the last observed AWS account ID from installer stack observations."""
        return (
            self.installer.observation.account_id
            if self.installer.observation is not None
            else None
        )

    def touch(self, now: datetime | None = None) -> datetime:
        """Record an update timestamp on workspace metadata."""
        timestamp = now or datetime.now(UTC)
        self.workspace.updated_at = timestamp
        return timestamp

    @classmethod
    def from_config(cls, config: WorkspaceConfig) -> WorkspaceState:
        """Create empty operational state for a newly initialized workspace."""
        del config
        return cls()
