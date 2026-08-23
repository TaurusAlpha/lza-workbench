"""Configuration repository and packaging schema models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lza_workbench.errors import LzaError


class ConfigurationRepositoryConfig(BaseModel):
    """Destination repository for the LZA configuration pipeline (Source of Truth)."""

    model_config = ConfigDict(extra="forbid", strict=False)

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
        if self.type == "codecommit":
            self.repository_name = self.repository_name or "lza-config-source"
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


class ConfigurationTemplateConfig(BaseModel):
    """Source of the starter LZA configuration."""

    model_config = ConfigDict(extra="forbid", strict=False)

    source: Literal["packaged", "local", "git"] = "packaged"
    name: str | None = "default"
    path: str | None = None
    repository: str | None = None
    ref: str | None = None


class PackagingExcludeConfig(BaseModel):
    """Files omitted from configuration archives."""

    model_config = ConfigDict(extra="forbid", strict=False)

    directories: list[str] = Field(default_factory=lambda: [".git", "backup"])
    files: list[str] = Field(default_factory=lambda: [".DS_Store"])


class PackagingConfig(BaseModel):
    """Configuration archive packaging settings."""

    model_config = ConfigDict(extra="forbid", strict=False)

    exclude: PackagingExcludeConfig = Field(default_factory=PackagingExcludeConfig)


class ConfigurationConfig(BaseModel):
    """Local LZA configuration and its pipeline destination."""

    model_config = ConfigDict(extra="forbid", strict=False)

    local_path: str = "aws-accelerator-config"
    template: ConfigurationTemplateConfig = Field(default_factory=ConfigurationTemplateConfig)
    repository: ConfigurationRepositoryConfig = Field(default_factory=ConfigurationRepositoryConfig)
    packaging: PackagingConfig = Field(default_factory=PackagingConfig)
