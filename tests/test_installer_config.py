"""Tests for shared installer configuration validation."""

from __future__ import annotations

import pytest

from lza_workbench.installer.config import validate_installer_configuration
from lza_workbench.installer.parameters import build_installer_cfn_parameters
from lza_workbench.workspace.models import AwsConfig, CustomerConfig, WorkspaceConfig


def complete_config() -> WorkspaceConfig:
    """Create a workspace configuration with all common installer values present."""
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
    )
    config.installer.options.management_account_email = "management@example.com"
    config.installer.options.log_archive_account_email = "log@example.com"
    config.installer.options.audit_account_email = "audit@example.com"
    return config


@pytest.mark.parametrize(
    ("source_type", "values", "expected_missing"),
    [
        ("github", {"owner": "", "repository_name": ""}, ["owner", "repository_name"]),
        ("codecommit", {"repository_name": ""}, ["repository_name"]),
        ("s3", {"bucket": "", "key": ""}, ["bucket", "key"]),
        ("codeconnection", {"connection_arn": ""}, ["connection_arn"]),
    ],
)
def test_validation_reports_required_fields_by_source_type(
    source_type: str,
    values: dict[str, str],
    expected_missing: list[str],
) -> None:
    config = complete_config()
    config.installer.source_code.repository_type = source_type  # type: ignore[assignment]
    for attribute, value in values.items():
        setattr(config.installer.source_code, attribute, value)

    result = validate_installer_configuration(config)

    assert [field.attribute for field in result.missing_fields] == expected_missing
    assert not result.is_complete


@pytest.mark.parametrize(
    ("source_type", "values"),
    [
        ("github", {"owner": "awslabs", "repository_name": "landing-zone-accelerator-on-aws"}),
        ("codecommit", {"repository_name": "aws-accelerator-codecommit"}),
        ("s3", {"bucket": "source-bucket", "key": "lza.zip"}),
        (
            "codeconnection",
            {"connection_arn": "arn:aws:codeconnections:us-east-1:123:connection/id"},
        ),
    ],
)
def test_validation_accepts_complete_source_types(
    source_type: str, values: dict[str, str]
) -> None:
    config = complete_config()
    config.installer.source_code.repository_type = source_type  # type: ignore[assignment]
    for attribute, value in values.items():
        setattr(config.installer.source_code, attribute, value)

    assert validate_installer_configuration(config).is_complete


@pytest.mark.parametrize(
    ("source_type", "values"),
    [
        ("github", {"owner": "github-owner", "repository_name": "github-repository"}),
        ("codecommit", {"repository_name": "codecommit-repository"}),
        ("s3", {"bucket": "source-bucket", "key": "installer/lza.zip"}),
        (
            "codeconnection",
            {"connection_arn": "arn:aws:codeconnections:us-east-1:123:connection/id"},
        ),
    ],
)
def test_parameter_mapping_preserves_every_source_type(
    source_type: str, values: dict[str, str]
) -> None:
    config = complete_config()
    config.installer.source_code.repository_type = source_type  # type: ignore[assignment]
    for attribute, value in values.items():
        setattr(config.installer.source_code, attribute, value)

    parameters = build_installer_cfn_parameters(config)

    assert parameters["RepositorySource"] == source_type
