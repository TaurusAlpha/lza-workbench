"""Tests for workspace initialization."""

from __future__ import annotations

from pathlib import Path

import pytest

from lza_workbench.cli.commands.workspace_init import (
    workspace_init_command as run_init,
)
from lza_workbench.errors import LzaError
from lza_workbench.workflows.workspace_init import (
    build_workspace_config,
)
from lza_workbench.workspace.config import load_workspace_config
from lza_workbench.workspace.paths import resolve_init_workspace_dir
from lza_workbench.workspace.state import load_workspace_state


def test_resolve_init_workspace_dir_uses_customer_slug(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    workspace_dir = resolve_init_workspace_dir("Example Customer")

    assert workspace_dir == tmp_path / "example-customer"


def test_build_workspace_config_uses_workspace_defaults() -> None:
    config = build_workspace_config(
        customer_name="Example Customer",
        customer_slug="example-customer",
        aws_profile="example-root",
        aws_region="eu-west-1",
        lza_version="v1.15.5",
    )

    assert config.configuration.template.source == "packaged"
    assert config.configuration.template.name == "default"
    assert config.configuration.local_path == "aws-accelerator-config"
    assert config.installer.local_path == "aws-accelerator-installer"


def test_run_init_dry_run_does_not_create_workspace(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "example-customer"

    run_init(
        customer_name="Example Customer",
        workspace_dir=workspace_dir,
        aws_profile="example-root",
        aws_region="eu-west-1",
        lza_version="v1.15.5",
        dry_run=True,
        force=False,
        skip_aws_check=True,
        interactive=False,
    )

    assert not workspace_dir.exists()


def test_run_init_creates_workspace_metadata(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "example-customer"

    run_init(
        customer_name="Example Customer",
        workspace_dir=workspace_dir,
        aws_profile="example-root",
        aws_region="eu-west-1",
        lza_version="v1.15.5",
        dry_run=False,
        force=False,
        skip_aws_check=True,
        interactive=False,
    )

    config = load_workspace_config(workspace_dir)
    state = load_workspace_state(workspace_dir)
    assert config.customer.slug == "example-customer"
    assert (workspace_dir / "lza-workspace.yaml").is_file()
    assert (workspace_dir / ".lza" / "state.json").is_file()
    assert (workspace_dir / config.installer.local_path).is_dir()
    assert not (workspace_dir / config.configuration.local_path).exists()
    assert state.initialized_at is None


def test_init_existing_directory_directs_user_to_import(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "existing"
    workspace_dir.mkdir()

    with pytest.raises(LzaError, match=r"lza import"):
        run_init(
            customer_name="Example Customer",
            workspace_dir=workspace_dir,
            aws_profile="example-root",
            aws_region="eu-west-1",
            lza_version="v1.15.5",
            dry_run=False,
            force=False,
            skip_aws_check=True,
            interactive=False,
        )
