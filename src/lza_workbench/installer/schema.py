"""Installer schema and configuration models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from lza_workbench.configuration.schema import ConfigurationRepositoryConfig
from lza_workbench.errors import LzaError
from lza_workbench.installer.versions import PACKAGED_INSTALLER_VERSION


class InstallerStackTemplateConfig(BaseModel):
    """Source of the CloudFormation template for the installer stack."""

    model_config = ConfigDict(extra="forbid", strict=False)

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
                f"landing-zone-accelerator-on-aws/{PACKAGED_INSTALLER_VERSION}/"
                "AWSAccelerator-InstallerStack.template"
            )
        return self


class InstallerSourceCodeConfig(BaseModel):
    """Source code consumed by the installer pipeline."""

    model_config = ConfigDict(extra="forbid", strict=False)

    repository_type: Literal["github", "codecommit", "s3", "codeconnection"] = "github"
    owner: str = "awslabs"
    github_secret_name: Literal["accelerator/github-token"] = "accelerator/github-token"
    repository_name: str | None = "landing-zone-accelerator-on-aws"
    branch: str | None = f"release/{PACKAGED_INSTALLER_VERSION}"
    bucket: str | None = None
    key: str | None = None
    connection_arn: str | None = None


class InstallerOptionsConfig(BaseModel):
    """CloudFormation parameters for the installer stack.

    Contains installer deployment options that are not owned by another workspace section.
    """

    model_config = ConfigDict(extra="forbid", strict=False)

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
        default="AWSAccelerator",
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
        default=True,
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
        default="lza-config-source",
        description="The name of an existing LZA configuration repository "
        "hosting the accelerator configuration.",
    )
    existing_config_repository_branch_name: str | None = Field(
        default="main",
        description="Specify the branch name of the existing LZA configuration repository.",
    )

    # Template Validation Rules
    @model_validator(mode="after")
    def validate_installer_options(self) -> InstallerOptionsConfig:
        """Enforces rules defined in the CloudFormation Rules block."""
        # Required Parameters For Code Connection
        if self.configuration_repository_location == "codeconnection":
            if not self.config_code_connection_arn:
                raise ValueError(
                    "config_code_connection_arn must be provided when "
                    "configuration_repository_location is set to 'codeconnection'. "
                    "Run `lza config plan` to set your CodeConnection ARN."
                )
            if not self.use_existing_config_repo:
                raise ValueError(
                    "use_existing_config_repo must be True when "
                    "configuration_repository_location is set to 'codeconnection'."
                )
            if not self.existing_config_repository_owner:
                raise ValueError(
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
                raise ValueError(
                    "config_code_connection_arn must be provided when "
                    "use_existing_config_repo is True and "
                    "configuration_repository_location is set to 'codeconnection'. "
                    "Run `lza config plan`."
                )
            elif self.configuration_repository_location == "codecommit":
                if not self.existing_config_repository_name:
                    self.existing_config_repository_name = "lza-config-source"
            if not self.existing_config_repository_branch_name:
                self.existing_config_repository_branch_name = "main"

        # Required Parameters For S3 Repo
        if self.configuration_repository_location == "s3":
            if (
                self.use_existing_config_repo
                or self.existing_config_repository_name
                or self.existing_config_repository_branch_name
            ):
                raise ValueError(
                    "Existing configuration repository parameters cannot be provided when "
                    "configuration_repository_location is set to 's3'."
                )

        return self

    @classmethod
    def sync_from_config_repo(
        cls, repo_config: ConfigurationRepositoryConfig, **kwargs
    ) -> InstallerOptionsConfig:
        try:
            repo_config = ConfigurationRepositoryConfig.model_validate(repo_config)
        except (ValidationError, ValueError) as err:
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
            "existing_config_repository_name": repo_config.repository_name or (
                "lza-config-source" if repo_config.type == "codecommit" else None
            ),
            "existing_config_repository_branch_name": repo_config.branch or "main",
        }

        merged_args = {**derived_options, **kwargs}

        try:
            return cls(**merged_args)
        except (ValidationError, ValueError) as err:
            raise LzaError(
                f"Failed to build Installer Options: {err}\n"
                "--> Please run `lza config plan` to fix configuration parameters."
            ) from err


class LzaInstaller(BaseModel):
    """Installer defaults persisted for later commands."""

    model_config = ConfigDict(extra="forbid", strict=False)

    local_path: str = "aws-accelerator-installer"
    stack_name: str = "AWSAccelerator-InstallerStack"
    stack_template: InstallerStackTemplateConfig = Field(
        default_factory=InstallerStackTemplateConfig
    )
    source_code: InstallerSourceCodeConfig = Field(default_factory=InstallerSourceCodeConfig)
    options: InstallerOptionsConfig = Field(default_factory=InstallerOptionsConfig)
    template_parameters: dict[str, str] = Field(default_factory=dict)


class PipelineInstaller(BaseModel):
    """A named installer LZA pipeline."""

    model_config = ConfigDict(extra="forbid", strict=False)

    name: str = "AWSAccelerator-Installer"
