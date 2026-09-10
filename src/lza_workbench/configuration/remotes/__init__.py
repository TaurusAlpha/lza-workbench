"""Configuration remotes package."""

from lza_workbench.configuration.remotes.git_remote import GitConfigurationRemote
from lza_workbench.configuration.remotes.protocol import ConfigurationRemote
from lza_workbench.configuration.remotes.s3 import S3ConfigurationRemote

__all__ = [
    "ConfigurationRemote",
    "GitConfigurationRemote",
    "S3ConfigurationRemote",
]
