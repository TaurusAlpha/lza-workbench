"""Tests for shared LZA installer version conversion rules."""

import pytest

from lza_workbench.installer.parameters import (
    apply_installer_parameter,
)
from lza_workbench.installer.versions import (
    branch_to_version,
    normalize_lza_version,
    version_to_branch,
)
from lza_workbench.workspace.schema import AwsConfig, CustomerConfig, WorkspaceConfig


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


# @pytest.mark.parametrize(
#     ("repository_type", "expected_branch"),
#     [
#         ("github", "release/v1.16.0"),
#         ("codecommit", "main"),
#         ("s3", "main"),
#         ("codeconnection", "main"),
#     ],
# )
# def test_cloudformation_parameters_use_source_specific_default_branch(
#     repository_type: str, expected_branch: str
# ) -> None:
#     config = WorkspaceConfig(
#         customer=CustomerConfig(name="Test Customer", slug="test-customer"),
#         aws=AwsConfig(profile="test-profile", region="us-east-1"),
#     )
#     config.lza.version = "1.16.0"
#     config.installer.source_code.repository_type = repository_type  # type: ignore[assignment]
#     config.installer.source_code.branch = "release/v1.16.0"

#     assert build_installer_cfn_parameters(config)["RepositoryBranchName"] == expected_branch


def test_collecting_repository_branch_persists_the_resolved_default() -> None:
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Test Customer", slug="test-customer"),
        aws=AwsConfig(profile="test-profile", region="us-east-1"),
    )
    config.lza.version = "1.16.0"

    apply_installer_parameter(config, "RepositoryBranchName", "")

    assert config.installer.source_code.branch == "release/v1.16.0"
    # assert config.installer.template_parameters["RepositoryBranchName"] == "release/v1.16.0"
