"""Validate installer configuration completeness before planning or deployment."""

from __future__ import annotations

from dataclasses import dataclass

from lza_workbench.workspace.schema import WorkspaceConfig


@dataclass(frozen=True)
class MissingInstallerConfigField:
    """A required installer configuration field with no usable value."""

    label: str
    section: str
    attribute: str
    value: str | None


@dataclass(frozen=True)
class InstallerConfigValidationResult:
    """The complete result of checking installer configuration requirements."""

    missing_fields: tuple[MissingInstallerConfigField, ...]

    @property
    def is_complete(self) -> bool:
        """Return whether every required installer configuration field is present."""
        return not self.missing_fields


def validate_installer_configuration(config: WorkspaceConfig) -> InstallerConfigValidationResult:
    """Report every required installer setting missing from a workspace configuration."""
    source_code = config.installer.source_code
    missing: list[MissingInstallerConfigField] = []

    def require(label: str, section: str, attribute: str, value: str | None) -> None:
        if not (value or "").strip():
            missing.append(
                MissingInstallerConfigField(
                    label=label,
                    section=section,
                    attribute=attribute,
                    value=value,
                )
            )

    if source_code.repository_type == "codecommit":
        require(
            "CodeCommit Repository Name",
            "installer.source_code",
            "repository_name",
            source_code.repository_name,
        )
    elif source_code.repository_type == "github":
        require(
            "GitHub Repository Owner",
            "installer.source_code",
            "owner",
            source_code.owner,
        )
        require(
            "GitHub Repository Name",
            "installer.source_code",
            "repository_name",
            source_code.repository_name,
        )
    elif source_code.repository_type == "s3":
        require("Source S3 Bucket", "installer.source_code", "bucket", source_code.bucket)
        require("Source S3 Key", "installer.source_code", "key", source_code.key)
    elif source_code.repository_type == "codeconnection":
        require(
            "Source CodeConnection ARN",
            "installer.source_code",
            "connection_arn",
            source_code.connection_arn,
        )

    options = config.installer.options
    require(
        "Management Account Email",
        "installer.options",
        "management_account_email",
        options.management_account_email,
    )
    require(
        "Log Archive Account Email",
        "installer.options",
        "log_archive_account_email",
        options.log_archive_account_email,
    )
    require(
        "Audit Account Email",
        "installer.options",
        "audit_account_email",
        options.audit_account_email,
    )
    require("Accelerator Prefix", "lza", "accelerator_prefix", config.lza.accelerator_prefix)

    return InstallerConfigValidationResult(missing_fields=tuple(missing))
