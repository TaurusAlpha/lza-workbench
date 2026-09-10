"""Installer domain and persistence models."""

from __future__ import annotations

from lza_workbench.installer.schema import (
    KNOWN_INSTALLER_PARAMETER_NAMES,
    InstallerApprovalConfig,
    InstallerEmailsConfig,
    InstallerOptionsConfig,
    InstallerSourceCodeConfig,
    InstallerStackTemplateConfig,
    LzaInstaller,
    PipelineInstaller,
)
from lza_workbench.installer.state import (
    InstallerState,
    load_installer_state,
    write_installer_state,
)

# Counterfactual aliases
InstallerDocument = LzaInstaller
InstallerRuntime = InstallerState

__all__ = [
    "KNOWN_INSTALLER_PARAMETER_NAMES",
    "InstallerApprovalConfig",
    "InstallerDocument",
    "InstallerEmailsConfig",
    "InstallerOptionsConfig",
    "InstallerRuntime",
    "InstallerSourceCodeConfig",
    "InstallerStackTemplateConfig",
    "InstallerState",
    "LzaInstaller",
    "PipelineInstaller",
    "load_installer_state",
    "write_installer_state",
]
