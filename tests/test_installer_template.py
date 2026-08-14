"""Tests for shared installer template domain logic."""

from __future__ import annotations

from pathlib import Path

import pytest

from lza_workbench.core.errors import LzaError
from lza_workbench.core.installer_template import INSTALLER_TEMPLATE_FILENAME
from lza_workbench.installer.template import (
    inspect_template_parameters,
    resolve_installer_template,
    validate_parameters_against_schema,
)
from lza_workbench.workspace.models import AwsConfig, CustomerConfig, LzaConfig, WorkspaceConfig


def test_template_resolution_and_parameter_inspection(tmp_path: Path) -> None:
    """Shared template functions use an existing workspace template without downloads."""
    workspace_dir = tmp_path / "example"
    template_dir = workspace_dir / "aws-accelerator-installer"
    template_dir.mkdir(parents=True)
    template_path = template_dir / INSTALLER_TEMPLATE_FILENAME
    template_path.write_text(
        '{"Parameters": {"RepositorySource": {"AllowedValues": ["github"]}}}',
        encoding="utf-8",
    )
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Example", slug="example"),
        aws=AwsConfig(profile="example", region="us-east-1"),
        lza=LzaConfig(version="v1.16.0"),
    )

    resolved = resolve_installer_template(workspace_dir, config, dry_run=False)

    assert resolved == template_path
    assert inspect_template_parameters(resolved) == {
        "RepositorySource": {"AllowedValues": ["github"]}
    }


def test_parameter_validation_uses_template_allowed_values() -> None:
    """Shared validation rejects a resolved value excluded by the template."""
    with pytest.raises(LzaError, match="Invalid parameter value 's3' for RepositorySource"):
        validate_parameters_against_schema(
            {"RepositorySource": "s3"},
            {"RepositorySource": {"AllowedValues": ["github", "codecommit"]}},
        )
