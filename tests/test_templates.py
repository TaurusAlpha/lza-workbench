"""Tests for LZA configuration template resolution and validation."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import pytest

from lza_workbench.config.templates import (
    DEFAULT_TEMPLATE_SOURCE,
    REQUIRED_TEMPLATE_FILES,
    ResolvedTemplateSource,
    resolve_template_source,
    validate_template,
)
from lza_workbench.errors import LzaError


def test_resolve_template_source_default() -> None:
    resolved = resolve_template_source(DEFAULT_TEMPLATE_SOURCE)
    assert isinstance(resolved, ResolvedTemplateSource)
    assert resolved.source == DEFAULT_TEMPLATE_SOURCE
    assert resolved.source_type == "bundled"
    assert resolved.config_dir.is_dir()
    assert (resolved.config_dir / "global-config.yaml").is_file()


def test_bundled_resources_are_in_the_resources_hierarchy() -> None:
    """Packaged assets have explicit resource categories."""
    installer_template = (
        files("lza_workbench.resources.installer_templates")
        / "v1.16.0"
        / "AWSAccelerator-InstallerStack.template"
    )
    workspace_example = files("lza_workbench.resources.workspace_examples") / "minimal.yaml"

    assert installer_template.is_file()
    assert workspace_example.is_file()


def test_resolve_template_source_local(tmp_path: Path) -> None:
    config_dir = tmp_path / "custom-template" / "aws-accelerator-config"
    config_dir.mkdir(parents=True)

    resolved = resolve_template_source(str(tmp_path / "custom-template"))
    assert resolved.source_type == "local"
    assert resolved.config_dir == config_dir


def test_resolve_template_source_remote_raises() -> None:
    with pytest.raises(LzaError, match="Remote template sources are not supported yet"):
        resolve_template_source("https://github.com/example/lza-template.git")


def test_validate_template_non_existent_directory(tmp_path: Path) -> None:
    non_existent = tmp_path / "does-not-exist"
    with pytest.raises(LzaError, match="Template directory does not exist"):
        validate_template(non_existent)


def test_validate_template_valid_directory(tmp_path: Path) -> None:
    config_dir = tmp_path / "aws-accelerator-config"
    config_dir.mkdir()
    for filename in REQUIRED_TEMPLATE_FILES:
        (config_dir / filename).write_text("# content\n", encoding="utf-8")

    # Should complete without error
    validate_template(config_dir)
