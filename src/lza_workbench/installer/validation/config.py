"""Installer configuration completeness validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lza_workbench.errors import LzaError
from lza_workbench.installer.versions import (
    PACKAGED_INSTALLER_VERSION,
    is_unwanted_lza_version,
    normalize_lza_version,
)

if TYPE_CHECKING:
    from lza_workbench.workspace.schema import WorkspaceConfig


@dataclass(frozen=True)
class MissingInstallerConfigField:
    label: str
    section: str
    attribute: str
    value: str | None


@dataclass(frozen=True)
class InstallerConfigValidationResult:
    missing_fields: tuple[MissingInstallerConfigField, ...]
    warnings: tuple[str, ...] = ()

    @property
    def is_complete(self) -> bool:
        return not self.missing_fields


class InstallerConfigValidationError(LzaError):
    def __init__(self, validation: InstallerConfigValidationResult) -> None:
        self.validation = validation
        missing = ", ".join(f"{s.section}.{s.attribute}" for s in validation.missing_fields)
        super().__init__(
            f"{len(validation.missing_fields)} required parameter(s) missing from "
            f"lza-workspace.yaml ({missing}). "
            "Run 'lza installer plan' to resolve and configure missing values."
        )


def validate_installer_configuration(config: WorkspaceConfig) -> InstallerConfigValidationResult:
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

    warnings: list[str] = []
    if is_unwanted_lza_version(config.lza.version):
        norm = normalize_lza_version(config.lza.version)
        warnings.append(
            f"Configured LZA version '{norm}' is old and unwanted (<= v1.5.0). "
            f"Consider upgrading to a supported version (e.g. {PACKAGED_INSTALLER_VERSION} or >= v1.5.1)."
        )

    return InstallerConfigValidationResult(
        missing_fields=tuple(missing),
        warnings=tuple(warnings),
    )


__all__ = [
    "InstallerConfigValidationError",
    "InstallerConfigValidationResult",
    "MissingInstallerConfigField",
    "validate_installer_configuration",
]
