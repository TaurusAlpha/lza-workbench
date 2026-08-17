"""Tests for consolidated installer template domain logic in installer/templates.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from lza_workbench.errors import LzaError
from lza_workbench.installer.templates import (
    INSTALLER_TEMPLATE_FILENAME,
    configure_anonymous_data,
    download_installer_template_content,
    inspect_template_parameters,
    resolve_installer_template,
    validate_parameters_against_schema,
)
from lza_workbench.workspace.schema import AwsConfig, CustomerConfig, LzaConfig, WorkspaceConfig


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


def test_download_installer_template_content_matching_fallback(tmp_path: Path) -> None:
    """When download fails and requested version matches packaged version, fallback is used."""
    fake_fallback = tmp_path / "fallback.template"
    fake_fallback.write_text('{"Description": "Packaged v1.16.0"}', encoding="utf-8")

    content = download_installer_template_content(
        url="http://invalid.invalid/template",
        fallback_version="v1.16.0",
        fallback_path=fake_fallback,
    )
    assert content == '{"Description": "Packaged v1.16.0"}'


def test_download_installer_template_content_mismatched_fallback(tmp_path: Path) -> None:
    """When download fails and requested version differs from packaged version, error is raised."""
    fake_fallback = tmp_path / "fallback.template"
    fake_fallback.write_text('{"Description": "Packaged v1.16.0"}', encoding="utf-8")

    with pytest.raises(LzaError, match="no local fallback template is available for this version"):
        download_installer_template_content(
            url="http://invalid.invalid/template",
            fallback_version="v1.15.5",
            fallback_path=fake_fallback,
        )


def test_download_installer_template_content_unavailable_fallback(tmp_path: Path) -> None:
    """When download fails, version matches, but fallback file is missing, error is raised."""
    non_existent = tmp_path / "does_not_exist.template"

    with pytest.raises(
        LzaError, match="packaged fallback template for version v1.16.0 was not found"
    ):
        download_installer_template_content(
            url="http://invalid.invalid/template",
            fallback_version="v1.16.0",
            fallback_path=non_existent,
        )


def test_download_installer_template_content_disabled_fallback() -> None:
    """When fallback_version is None, download failure raises error without checking fallback."""
    with pytest.raises(LzaError, match="fallback is disabled"):
        download_installer_template_content(
            url="http://invalid.invalid/template",
            fallback_version=None,
        )


def test_resolve_installer_template_dry_run_mismatched_version(tmp_path: Path) -> None:
    """In dry run, when local template is missing and version differs, do not return packaged."""
    workspace_dir = tmp_path / "example"
    (workspace_dir / "aws-accelerator-installer").mkdir(parents=True)
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Example", slug="example"),
        aws=AwsConfig(profile="example", region="us-east-1"),
        lza=LzaConfig(version="v1.15.5"),
    )

    resolved = resolve_installer_template(workspace_dir, config, dry_run=True)
    assert not resolved.exists()
    assert resolved.name == INSTALLER_TEMPLATE_FILENAME


def test_configure_anonymous_data() -> None:
    """Verify configure_anonymous_data modifies JSON Mappings accurately."""
    sample = (
        '{"Mappings": {"Settings": {"SendAnonymizedData": {"Data": "Yes"}}}}'
    )
    disabled = configure_anonymous_data(sample, False)
    assert '"Data": "No"' in disabled

    enabled = configure_anonymous_data(disabled, True)
    assert '"Data": "Yes"' in enabled
