"""Tests for shared LZA installer version conversion rules."""

import pytest

from lza_workbench.installer.parameters import build_installer_cfn_parameters
from lza_workbench.installer.versions import (
    branch_to_version,
    normalize_lza_version,
    version_to_branch,
)
from lza_workbench.workspace.models import AwsConfig, CustomerConfig, WorkspaceConfig


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("latest", "latest"),
        ("main", "latest"),
        ("master", "latest"),
        ("v1.16.0", "v1.16.0"),
        ("1.16.0", "v1.16.0"),
        ("release/v1.16.0", "v1.16.0"),
    ],
)
def test_normalize_lza_version(value: str, expected: str) -> None:
    assert normalize_lza_version(value) == expected


@pytest.mark.parametrize(
    ("version", "branch"),
    [
        ("latest", "main"),
        ("main", "main"),
        ("master", "main"),
        ("v1.16.0", "release/v1.16.0"),
        ("1.16.0", "release/v1.16.0"),
        ("release/v1.16.0", "release/v1.16.0"),
    ],
)
def test_version_to_branch(version: str, branch: str) -> None:
    assert version_to_branch(version) == branch


@pytest.mark.parametrize(
    ("branch", "version"),
    [
        ("", "Unknown"),
        ("main", "latest"),
        ("master", "latest"),
        ("release/v1.16.0", "v1.16.0"),
        ("v1.16.0", "v1.16.0"),
        ("1.16.0", "v1.16.0"),
    ],
)
def test_branch_to_version(branch: str, version: str) -> None:
    assert branch_to_version(branch) == version


def test_cloudformation_parameters_use_version_to_branch() -> None:
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
    )
    config.lza.version = "release/v1.16.0"
    config.installer.source_code.branch = None

    assert build_installer_cfn_parameters(config)["RepositoryBranchName"] == "release/v1.16.0"
