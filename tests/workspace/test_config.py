"""Tests for loading the typed workspace YAML configuration."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from lza_workbench.workspace.config import load_workspace_config, write_workspace_config
from lza_workbench.workspace.schema import AwsConfig, CustomerConfig, WorkspaceConfig

WORKSPACE_EXAMPLES_DIR = (
    Path(__file__).parents[2] / "src" / "lza_workbench" / "resources" / "workspace_examples"
)


def _create_test_workspace(target_dir: Path, example_file: str) -> Path:
    """Helper to place an example YAML into a mock workspace directory as lza-workspace.yaml."""
    source_path = WORKSPACE_EXAMPLES_DIR / example_file
    destination = target_dir / "lza-workspace.yaml"
    shutil.copy(source_path, destination)
    return target_dir


@pytest.mark.parametrize(
    "filename",
    ["minimal.yaml", "full.yaml", "configuration-only.yaml", "installer-only.yaml"],
)
def test_workspace_examples_load(filename: str, tmp_path: Path) -> None:
    workspace_dir = _create_test_workspace(tmp_path, filename)
    config = load_workspace_config(workspace_dir)

    assert config.customer.slug == "example-customer"
    assert config.aws.region == "eu-west-1"


def test_minimal_workspace_uses_nested_defaults(tmp_path: Path) -> None:
    workspace_dir = _create_test_workspace(tmp_path, "minimal.yaml")
    config = load_workspace_config(workspace_dir)

    assert config.lza.version == "1.15.5"
    assert config.installer.local_path == "aws-accelerator-installer"
    assert config.configuration.template.source == "packaged"
    assert config.pipelines.configuration.name == "AWSAccelerator-Pipeline"


def test_full_workspace_preserves_explicit_values(tmp_path: Path) -> None:
    workspace_dir = _create_test_workspace(tmp_path, "full.yaml")
    config = load_workspace_config(workspace_dir)

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
        load_workspace_config(tmp_path)


@pytest.mark.parametrize("field", ["access_key", "secret_access_key"])
def test_workspace_rejects_persisted_aws_secrets(tmp_path: Path, field: str) -> None:
    (tmp_path / "lza-workspace.yaml").write_text(
        "customer:\n  name: Example\n  slug: example\naws:\n"
        f"  profile: example-root\n  {field}: value\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not supported"):
        load_workspace_config(tmp_path)


def test_workspace_writer_never_serializes_secret_keys(tmp_path: Path) -> None:
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Example", slug="example"),
        aws=AwsConfig(profile="example-root", role_arn="arn:aws:iam::123456789012:role/Lza"),
    )

    write_workspace_config(tmp_path, config)

    serialized = (tmp_path / "lza-workspace.yaml").read_text(encoding="utf-8")
    assert "access_key" not in serialized
    assert "secret_access_key" not in serialized
    assert "role_arn" in serialized
