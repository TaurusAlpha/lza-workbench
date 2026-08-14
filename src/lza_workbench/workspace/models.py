from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lza_workbench.core.errors import LzaError


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


# LZA Configuration
class ConfigurationRepositoryConfig(WorkspaceModel):
    """Destination repository for the LZA configuration pipeline (Source of Truth)."""

    type: Literal["s3", "codecommit", "codeconnection", "git"] = "codecommit"
    bucket: str | None = None
    prefix: str = "zipped/"
    key: str = "aws-accelerator-config.zip"
    repository_name: str | None = None
    repository: str | None = None
    branch: str | None = None
    codeconnection_arn: str | None = None
    owner: str | None = None

    @model_validator(mode="after")
    def validate_configuration_repository(self) -> ConfigurationRepositoryConfig:
        # TODO(refactor): Apply this during configuration planning, where the parent AwsConfig
        # is available. A repository model alone cannot derive an account-specific bucket.
        # if self.type == "s3" and not self.bucket:
        #     self.bucket = f"aws-accelerator-config-{aws.account_id}-{aws.region}"
        if self.type == "codecommit":
            self.repository_name = self.repository_name or "aws-accelerator-config"
            self.branch = self.branch or "main"

        elif self.type == "codeconnection":
            missing_fields = []
            if not self.codeconnection_arn:
                missing_fields.append("codeconnection_arn")
            if not self.owner:
                missing_fields.append("owner")
            if not self.repository_name:
                missing_fields.append("repository_name")

            if missing_fields:
                fields_str = ", ".join(missing_fields)
                raise LzaError(
                    f"Missing required CodeConnection parameter(s): [{fields_str}]. "
                    "Run `lza config plan` to set up your repository configuration."
                )
            self.branch = self.branch or "main"

        return self


class ConfigurationTemplateConfig(WorkspaceModel):
    """Source of the starter LZA configuration."""

    source: Literal["packaged", "local", "git"] = "packaged"
    name: str | None = "default"
    path: str | None = None
    repository: str | None = None
    ref: str | None = None


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


# LZA Installer
class InstallerStackTemplateConfig(WorkspaceModel):
    """Source of the CloudFormation template for the installer stack."""

    source: Literal["amazon", "local", "git", "s3"] = "amazon"
    path: str | None = None
    repository: str | None = None
    ref: str | None = None

    @model_validator(mode="after")
    def validate_source(self) -> InstallerStackTemplateConfig:
        """Validate source and set default Amazon path if empty."""
        if self.source == "amazon" and not self.path:
            self.path = (
                "https://s3.amazonaws.com/solutions-reference/"
                f"landing-zone-accelerator-on-aws/{LzaConfig().version}/"
                "AWSAccelerator-InstallerStack.template"
            )
        return self


class InstallerSourceCodeConfig(WorkspaceModel):
    """Source code consumed by the installer pipeline."""

    repository_type: Literal["github", "codecommit", "s3", "codeconnection"] = "github"
    owner: str | None = "awslabs"
    repository_name: str | None = "landing-zone-accelerator-on-aws"
    branch: str | None = None
    bucket: str | None = None
    key: str | None = None
    connection_arn: str | None = None

    # TODO(refactor): Move these deployment-completeness checks to installer plan/deploy.
    # WorkspaceConfig must support incomplete drafts created by `lza init`.
    #
    # @model_validator(mode="after")
    # def validate_repository_type(self) -> InstallerSourceCodeConfig:
    #     if self.repository_type == "github":
    #         if not self.owner or not self.repository_name:
    #             raise LzaError("GitHub repository must have an 'owner' and 'repository_name'.")
    #     elif self.repository_type == "s3":
    #         if not self.bucket or not self.key:
    #             raise LzaError("S3 repository type requires both 'bucket' and 'key'.")
    #     elif self.repository_type == "codeconnection":
    #         if not self.connection_arn:
    #             raise LzaError("CodeConnection type requires 'connection_arn'.")
    #     return self

class InstallerOptionsConfig(WorkspaceModel):
    """CloudFormation parameters for the installer stack.

    Contains all 18 parameters from the CloudFormation template metadata.
    """

    # Source Code Repository Configuration
    repository_source: Literal["github", "codecommit", "s3"] = Field(
        default="github",
        description="Specify the location to use to host the LZA source code.",
    )
    repository_owner: str = Field(
        default="awslabs",
        description="The owner of the repository containing the accelerator code. (GitHub Only)",
    )
    repository_name: str = Field(
        default="landing-zone-accelerator-on-aws",
        description="The name of the git repository hosting the accelerator code.",
    )
    repository_branch_name: str = Field(
        default_factory=lambda: f"release/{LzaConfig().version}",
        min_length=1,
        description="The name of the git branch to use for installation.",
    )

    # Pipeline Configuration
    enable_approval_stage: bool = Field(
        default=False,
        description="Select yes to add a Manual Approval stage to accelerator pipeline.",
    )
    approval_stage_notify_email_list: list[str] = Field(
        default_factory=list,
        description="Provide list of email ids to receive manual "
        "approval stage notification email.",
    )

    # Mandatory Accounts Configuration
    management_account_email: str | None = Field(
        default=None,
        description="The management (primary) account email.",
    )
    log_archive_account_email: str | None = Field(
        default=None,
        description="The log archive account email.",
    )
    audit_account_email: str | None = Field(
        default=None,
        description="The security audit account (also referred to as the audit account).",
    )

    # Environment Configuration
    control_tower_enabled: bool = Field(
        default=True,
        description="Select yes if deploying to a Control Tower environment.",
    )
    accelerator_prefix: str = Field(
        default=LzaConfig().accelerator_prefix,
        max_length=15,
        pattern=r"^[A-Za-z0-9-]+$",
        description="The prefix value for accelerator deployed resources.",
    )
    enable_diagnostics_pack: bool = Field(
        default=True,
        description="Select Yes if deploying the solution with diagnostics pack enabled.",
    )
    anonymous_data: bool = False

    # Config Repository Configuration
    configuration_repository_location: Literal["codecommit", "s3", "codeconnection"] = Field(
        default="codecommit",
        description="Specify the location to use to host the LZA configuration files.",
    )
    use_existing_config_repo: bool = Field(
        default=False,
        description="Select Yes if deploying the solution with an existing "
        "configuration repository.",
    )
    config_code_connection_arn: str | None = Field(
        default=None,
        description="The ARN of an AWS CodeConnection referencing your existing "
        "LZA configuration repository.",
    )
    existing_config_repository_owner: str | None = Field(
        default=None,
        description="The owner ID or namespace of the LZA configuration "
        "repository accessed through CodeConnection.",
    )
    existing_config_repository_name: str | None = Field(
        default=None,
        description="The name of an existing LZA configuration repository "
        "hosting the accelerator configuration.",
    )
    existing_config_repository_branch_name: str | None = Field(
        default=None,
        description="Specify the branch name of the existing LZA configuration repository.",
    )

    # Template Validation Rules
    @model_validator(mode="after")
    def validate_installer_options(self) -> InstallerOptionsConfig:
        """Enforces rules defined in the CloudFormation Rules block."""

        # TODO(refactor): Validate this in installer plan/deploy, not while loading a draft.
        # if self.enable_approval_stage and not self.approval_stage_notify_email_list:
        #     raise LzaError(
        #         "Approval Stage notification email list is required when approval is enabled."
        #     )

        # Required Parameters For Code Connection
        if self.configuration_repository_location == "codeconnection":
            if not self.config_code_connection_arn:
                raise LzaError(
                    "config_code_connection_arn must be provided when "
                    "configuration_repository_location is set to 'codeconnection'. "
                    "Run `lza config plan` to set your CodeConnection ARN."
                )
            if not self.use_existing_config_repo:
                raise LzaError(
                    "use_existing_config_repo must be True when "
                    "configuration_repository_location is set to 'codeconnection'."
                )
            if not self.existing_config_repository_owner:
                raise LzaError(
                    "existing_config_repository_owner must be populated when "
                    "configuration_repository_location is set to 'codeconnection'. "
                    "Run `lza config plan` to set the repository owner."
                )

        # Required Parameters For Existing Repo
        if self.use_existing_config_repo:
            if (
                self.configuration_repository_location == "codeconnection"
                and not self.config_code_connection_arn
            ):
                raise LzaError(
                    "config_code_connection_arn must be provided when "
                    "use_existing_config_repo is True and "
                    "configuration_repository_location is set to 'codeconnection'. "
                    "Run `lza config plan`."
                )
            elif self.configuration_repository_location == "codecommit":
                if not self.existing_config_repository_name:
                    raise LzaError(
                        "existing_config_repository_name must be provided when "
                        "use_existing_config_repo is True and "
                        "configuration_repository_location is set to 'codecommit'. "
                        "Run `lza config plan`."
                    )
            if not self.existing_config_repository_branch_name:
                self.existing_config_repository_branch_name = "main"

        # Required Parameters For S3 Repo
        if self.configuration_repository_location == "s3":
            if (
                self.use_existing_config_repo
                or self.existing_config_repository_name
                or self.existing_config_repository_branch_name
            ):
                raise LzaError(
                    "Existing configuration repository parameters cannot be provided when "
                    "configuration_repository_location is set to 's3'."
                )

        # TODO(refactor): Validate required account emails in installer plan/deploy. They are
        # intentionally absent from a newly initialized workspace draft.
        # missing_emails = []
        # if not self.management_account_email:
        #     missing_emails.append("management_account_email")
        # if not self.log_archive_account_email:
        #     missing_emails.append("log_archive_account_email")
        # if not self.audit_account_email:
        #     missing_emails.append("audit_account_email")
        # if missing_emails:
        #     raise LzaError(
        #         f"Missing required mandatory account email(s): {', '.join(missing_emails)}."
        #     )

        return self

    @classmethod
    def sync_from_config_repo(
        cls, repo_config: ConfigurationRepositoryConfig, **kwargs
    ) -> InstallerOptionsConfig:
        try:
            repo_config = ConfigurationRepositoryConfig.model_validate(repo_config)
        except LzaError as err:
            raise LzaError(
                f"Configuration Repository is invalid or incomplete: {err}\n"
                "--> Please run `lza config plan` to configure your workspace."
            ) from err

        is_existing = repo_config.type in ("codecommit", "codeconnection")

        derived_options = {
            "configuration_repository_location": repo_config.type,
            "use_existing_config_repo": is_existing,
            "config_code_connection_arn": repo_config.codeconnection_arn,
            "existing_config_repository_owner": repo_config.owner,
            "existing_config_repository_name": repo_config.repository_name,
            "existing_config_repository_branch_name": repo_config.branch,
        }

        # Merge derived values with explicit kwargs (kwargs take precedence)
        merged_args = {**derived_options, **kwargs}

        # 3. Instantiate and validate options
        try:
            return cls(**merged_args)
        except LzaError as err:
            raise LzaError(
                f"Failed to build Installer Options: {err}\n"
                "--> Please run `lza config plan` to fix configuration parameters."
            ) from err


class LzaInstaller(WorkspaceModel):
    """Installer defaults persisted for later commands."""

    local_path: str = "aws-accelerator-installer"
    stack_name: str = "AWSAccelerator-InstallerStack"
    stack_template: InstallerStackTemplateConfig = Field(
        default_factory=InstallerStackTemplateConfig
    )
    source_code: InstallerSourceCodeConfig = Field(default_factory=InstallerSourceCodeConfig)
    options: InstallerOptionsConfig = Field(default_factory=InstallerOptionsConfig)


class PipelineConfig(WorkspaceModel):
    """A named configuration LZA pipeline."""

    name: str = "AWSAccelerator-Pipeline"
    watch: bool = True
    execute: bool = True
    detailed_error_reporting: bool = False
    poll_interval_seconds: int = 30


class PipelineInstaller(WorkspaceModel):
    """A named installer LZA pipeline."""

    name: str = "AWSAccelerator-Installer"


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
