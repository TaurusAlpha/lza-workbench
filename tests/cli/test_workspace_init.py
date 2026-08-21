"""Tests for workspace initialization CLI command."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from lza_workbench.cli import app
from lza_workbench.workspace.config import load_workspace_config
from lza_workbench.workspace.paths import resolve_init_workspace_dir
from lza_workbench.workspace.state import load_workspace_state


def test_resolve_init_workspace_dir_uses_customer_slug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    workspace_dir = resolve_init_workspace_dir("Example Customer")
    assert workspace_dir == tmp_path / "example-customer"


def test_cli_init_dry_run_does_not_create_workspace(
    tmp_path: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    workspace_dir = tmp_path / "example-customer"

    result = cli_runner.invoke(
        app,
        [
            "init",
            "Example Customer",
            "--workspace-dir",
            str(workspace_dir),
            "--aws-profile",
            "example-root",
            "--aws-region",
            "eu-west-1",
            "--lza-version",
            "v1.15.5",
            "--dry-run",
            "--skip-aws-check",
        ],
    )

    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert not workspace_dir.exists()


def test_cli_init_creates_workspace_metadata(
    tmp_path: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    workspace_dir = tmp_path / "example-customer"

    result = cli_runner.invoke(
        app,
        [
            "init",
            "Example Customer",
            "--workspace-dir",
            str(workspace_dir),
            "--aws-profile",
            "example-root",
            "--aws-region",
            "eu-west-1",
            "--lza-version",
            "v1.15.5",
            "--skip-aws-check",
        ],
    )

    assert result.exit_code == 0
    config = load_workspace_config(workspace_dir)
    state = load_workspace_state(workspace_dir)
    assert config.customer.slug == "example-customer"
    assert (workspace_dir / "lza-workspace.yaml").is_file()
    assert (workspace_dir / ".lza" / "state.json").is_file()
    assert (workspace_dir / config.installer.local_path).is_dir()
    assert not (workspace_dir / config.configuration.local_path).exists()
    assert state.initialized_at is None


def test_cli_init_existing_directory_directs_user_to_import(
    tmp_path: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    workspace_dir = tmp_path / "existing"
    workspace_dir.mkdir()

    result = cli_runner.invoke(
        app,
        [
            "init",
            "Example Customer",
            "--workspace-dir",
            str(workspace_dir),
            "--aws-profile",
            "example-root",
            "--aws-region",
            "eu-west-1",
            "--lza-version",
            "v1.15.5",
            "--skip-aws-check",
        ],
    )

    assert result.exit_code == 1
    assert "lza import" in (result.output or str(result.exception))
