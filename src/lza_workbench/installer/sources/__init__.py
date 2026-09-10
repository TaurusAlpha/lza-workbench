"""Installer source providers package."""

from lza_workbench.installer.sources.codecommit import CodeCommitInstallerSourceProvider
from lza_workbench.installer.sources.codeconnection import (
    CodeConnectionInstallerSourceProvider,
)
from lza_workbench.installer.sources.github import GitHubInstallerSourceProvider
from lza_workbench.installer.sources.protocol import InstallerSourceProvider
from lza_workbench.installer.sources.s3 import S3InstallerSourceProvider

__all__ = [
    "CodeCommitInstallerSourceProvider",
    "CodeConnectionInstallerSourceProvider",
    "GitHubInstallerSourceProvider",
    "InstallerSourceProvider",
    "S3InstallerSourceProvider",
]
