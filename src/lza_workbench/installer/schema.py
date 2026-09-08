"""Installer schema and configuration models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from lza_workbench.installer.versions import PACKAGED_INSTALLER_VERSION

KNOWN_INSTALLER_PARAMETER_NAMES = frozenset(
    {
        "RepositorySource",
        "RepositoryOwner",
        "RepositoryName",
        "RepositoryBranchName",
        "RepositoryBucketName",
        "RepositoryBucketObject",
        "EnableApprovalStage",
        "ApprovalStageNotifyEmailList",
        "ManagementAccountEmail",
        "LogArchiveAccountEmail",
        "AuditAccountEmail",
        "ControlTowerEnabled",
        "AcceleratorPrefix",
        "ConfigurationRepositoryLocation",
        "UseExistingConfigRepo",
        "ConfigCodeConnectionArn",
        "ExistingConfigRepositoryOwner",
        "ExistingConfigRepositoryName",
        "ExistingConfigRepositoryBranchName",
        "EnableDiagnosticsPack",
    }
)


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

    repository_type: Literal["github", "codecommit", "s3", "codeconnection"] = Field(
        default="github",
        description="Installer source location.",
    )
    owner: str = Field(
        default="awslabs",
        description="Installer repository owner.",
    )
    github_secret_name: Literal["accelerator/github-token"] = Field(
        default="accelerator/github-token",
        description="Secrets Manager secret name for GitHub token.",
    )
    repository_name: str | None = Field(
        default="landing-zone-accelerator-on-aws",
        description="Installer repository name.",
    )
    branch: str | None = Field(
        default=f"release/{PACKAGED_INSTALLER_VERSION}",
        description="Installer source branch name.",
    )
    bucket: str | None = Field(
        default=None,
        description="S3 bucket for installer source.",
    )
    key: str | None = Field(
        default=None,
        description="S3 key for installer source archive.",
    )
    connection_arn: str | None = Field(
        default=None,
        description="CodeConnection ARN for installer source.",
    )


class InstallerOptionsConfig(BaseModel):
    """CloudFormation parameters for the installer stack.

    Contains installer deployment options that are not owned by another workspace section.
    """

    model_config = ConfigDict(extra="forbid", strict=False)

    # Pipeline Configuration
    enable_approval_stage: bool = Field(
        default=False,
        description="Add a manual approval stage to pipeline.",
    )
    approval_stage_notify_email_list: list[str] = Field(
        default_factory=list,
        description="Emails to notify for manual approval.",
    )

    # Mandatory Accounts Configuration
    management_account_email: str | None = Field(
        default=None,
        description="Management account email.",
    )
    log_archive_account_email: str | None = Field(
        default=None,
        description="Log Archive account email.",
    )
    audit_account_email: str | None = Field(
        default=None,
        description="Security Audit account email.",
    )

    # Environment Configuration
    control_tower_enabled: bool = Field(
        default=True,
        description="Deploying in Control Tower environment.",
    )
    enable_diagnostics_pack: bool = Field(
        default=True,
        description="Enable pipeline diagnostics pack.",
    )
    anonymous_data: bool = False

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
    extra_parameters: dict[str, str] = Field(default_factory=dict)

    @field_validator("extra_parameters")
    @classmethod
    def reject_known_extra_parameters(cls, value: dict[str, str]) -> dict[str, str]:
        conflicting = sorted(set(value) & KNOWN_INSTALLER_PARAMETER_NAMES)
        if conflicting:
            raise ValueError(
                "installer.extra_parameters cannot override known installer parameter(s): "
                f"{', '.join(conflicting)}"
            )
        return value


class PipelineInstaller(BaseModel):
    """A named installer LZA pipeline."""

    model_config = ConfigDict(extra="forbid", strict=False)

    name: str = "AWSAccelerator-Installer"
