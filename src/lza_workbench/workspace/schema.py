"""Top-level workspace schema models for LZA Workbench."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lza_workbench.config.schema import ConfigurationConfig
from lza_workbench.installer.schema import LzaInstaller, PipelineInstaller


class WorkspaceModel(BaseModel):
    """Base model for forward-compatible workspace metadata."""

    model_config = ConfigDict(extra="forbid", strict=False)


class CustomerConfig(WorkspaceModel):
    """Customer identity stored in lza-workspace.yaml."""

    name: str
    slug: str


class AwsConfig(WorkspaceModel):
    """AWS defaults stored in lza-workspace.yaml."""

    account_id: str | None = None
    region: str = "us-east-1"
    profile: str | None = None
    role_arn: str | None = None

    @model_validator(mode="after")
    def require_profile(self) -> AwsConfig:
        """Require the externally managed AWS profile used by this workspace."""
        if not (self.profile or self.role_arn or "").strip():
            raise ValueError("AWS configuration requires a profile or role_arn.")
        return self


class LzaConfig(WorkspaceModel):
    """Landing Zone Accelerator settings stored in lza-workspace.yaml."""

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
