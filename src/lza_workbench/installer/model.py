"""Installer domain models."""

from __future__ import annotations

from lza_workbench.installer.schema import (
    KNOWN_INSTALLER_PARAMETER_NAMES,
    InstallerOptionsConfig,
    InstallerSourceCodeConfig,
    InstallerStackTemplateConfig,
    LzaInstaller,
    PipelineInstaller,
)
from lza_workbench.installer.state import (
    record_installer_deployment,
    record_installer_deployment_failure,
)

# Counterfactual aliases
InstallerDocument = LzaInstaller

__all__ = [
    "KNOWN_INSTALLER_PARAMETER_NAMES",
    "InstallerDocument",
    "InstallerOptionsConfig",
    "InstallerSourceCodeConfig",
    "InstallerStackTemplateConfig",
    "LzaInstaller",
    "PipelineInstaller",
    "record_installer_deployment",
    "record_installer_deployment_failure",
]
