"""Tests for loading the typed workspace YAML configuration."""

from __future__ import annotations

from pathlib import Path

import pytest

from lza_workbench.core.workspace import load_workspace_config

CONFIG_DIR = Path(__file__).parents[1] / "src" / "lza_workbench" / "config" / "examples"


@pytest.mark.parametrize(
    "filename",
    ["minimal.yaml", "full.yaml", "configuration-only.yaml", "installer-only.yaml"],
)
def test_workspace_examples_load(filename: str) -> None:
    config = load_workspace_config(CONFIG_DIR / filename)

    assert config.customer.slug == "example-customer"
    assert config.aws.region == "eu-west-1"


def test_minimal_workspace_uses_nested_defaults() -> None:
    config = load_workspace_config(CONFIG_DIR / "minimal.yaml")

    assert config.lza.version == "v1.15.5"
    assert config.installer.local_path == "aws-accelerator-installer"
    assert config.configuration.template.source == "packaged"
    assert config.pipelines.configuration.name == "AWSAccelerator-Pipeline"


def test_full_workspace_preserves_explicit_values() -> None:
    config = load_workspace_config(CONFIG_DIR / "full.yaml")

    assert config.installer.source_code.repository_name == "landing-zone-accelerator-on-aws"
    assert config.configuration.repository.bucket == (
        "aws-accelerator-config-123456789012-eu-west-1"
    )
    assert config.configuration.packaging.exclude.directories == [".git", "backup"]


def test_workspace_rejects_unknown_settings(tmp_path: Path) -> None:
    config_path = tmp_path / "lza-workspace.yaml"
    config_path.write_text(
        """\
customer:
  name: Example Customer
  slug: example-customer
aws:
  profile: example-root
  region: eu-west-1
cli_defaults:
  watch_pipline: true
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="watch_pipline"):
        load_workspace_config(config_path)
