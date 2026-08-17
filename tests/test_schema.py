"""Tests for split schema models in workspace, configuration, and installer packages."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lza_workbench.configuration.schema import (
    ConfigurationConfig,
    ConfigurationRepositoryConfig,
)
from lza_workbench.installer.schema import (
    InstallerOptionsConfig,
    LzaInstaller,
)
from lza_workbench.workspace.schema import (
    AwsConfig,
    CliConfig,
    CustomerConfig,
    LzaConfig,
    PipelinesConfig,
    WorkspaceConfig,
)


def test_workspace_schema_composition() -> None:
    """Verify WorkspaceConfig composes domain schemas properly."""
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Acme Corp", slug="acme-corp"),
        aws=AwsConfig(profile="acme-admin", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0"),
        installer=LzaInstaller(),
        configuration=ConfigurationConfig(),
        pipelines=PipelinesConfig(),
        cli_defaults=CliConfig(),
    )
    assert config.customer.slug == "acme-corp"
    assert config.installer.source_code.repository_type == "github"
    assert config.configuration.repository.type == "codecommit"
    assert config.schema_version == 2


def test_forbids_extra_fields_across_submodels() -> None:
    """All schema models enforce strict attribute definitions."""
    with pytest.raises(ValidationError):
        CustomerConfig(name="Acme", slug="acme", unexpected="invalid")  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        ConfigurationRepositoryConfig(type="s3", invalid_extra="value")  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        InstallerOptionsConfig(invalid_param="bad")  # type: ignore[call-arg]


def test_installer_options_sync_from_config_repo() -> None:
    """Verify synchronization between config repository and installer options."""
    repo = ConfigurationRepositoryConfig(
        type="codecommit",
        repository_name="custom-repo",
        branch="develop",
    )
    options = InstallerOptionsConfig.sync_from_config_repo(repo)
    assert options.configuration_repository_location == "codecommit"
    assert options.use_existing_config_repo is True
    assert options.existing_config_repository_name == "custom-repo"
    assert options.existing_config_repository_branch_name == "develop"
