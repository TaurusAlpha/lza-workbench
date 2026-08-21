"""Tests for importing existing LZA configurations CLI command."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from lza_workbench.cli import app
from lza_workbench.configuration.templates import REQUIRED_TEMPLATE_FILES
from lza_workbench.workspace.config import load_workspace_config
from lza_workbench.workspace.state import load_workspace_state


def _write_required_files(config_dir: Path) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    for filename in REQUIRED_TEMPLATE_FILES:
        (config_dir / filename).write_text("{}\n", encoding="utf-8")


def _make_configuration(tmp_path: Path) -> tuple[Path, Path]:
    workspace_dir = tmp_path / "workspace"
    config_dir = workspace_dir / "aws-accelerator-config"
    _write_required_files(config_dir)
    return workspace_dir, config_dir


def test_cli_import_creates_metadata_without_modifying_configuration(
    tmp_path: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    workspace_dir, config_dir = _make_configuration(tmp_path)
    config_file = config_dir / REQUIRED_TEMPLATE_FILES[0]
    content_before = config_file.read_text(encoding="utf-8")

    result = cli_runner.invoke(
        app,
        [
            "import",
            str(workspace_dir),
            "--customer-name",
            "Example Customer",
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
    assert config.configuration.local_path == "aws-accelerator-config"
    assert config.configuration.template.source == "local"
    assert load_workspace_state(workspace_dir)
    assert config_file.read_text(encoding="utf-8") == content_before


def test_cli_import_dry_run_does_not_write_metadata(
    tmp_path: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    workspace_dir, _ = _make_configuration(tmp_path)

    result = cli_runner.invoke(
        app,
        [
            "import",
            str(workspace_dir),
            "--customer-name",
            "Example Customer",
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
    assert not (workspace_dir / "lza-workspace.yaml").exists()
    assert not (workspace_dir / ".lza").exists()


def test_cli_import_invalid_metadata_requires_force(
    tmp_path: Path,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    workspace_dir, _ = _make_configuration(tmp_path)
    (workspace_dir / "lza-workspace.yaml").write_text("invalid: true\n", encoding="utf-8")

    result_err = cli_runner.invoke(
        app,
        [
            "import",
            str(workspace_dir),
            "--customer-name",
            "Example Customer",
            "--aws-profile",
            "example-root",
            "--aws-region",
            "eu-west-1",
            "--lza-version",
            "v1.15.5",
            "--skip-aws-check",
        ],
    )
    assert result_err.exit_code == 1
    assert "--force" in (result_err.output or str(result_err.exception))

    result_force = cli_runner.invoke(
        app,
        [
            "import",
            str(workspace_dir),
            "--customer-name",
            "Example Customer",
            "--aws-profile",
            "example-root",
            "--aws-region",
            "eu-west-1",
            "--lza-version",
            "v1.15.5",
            "--force",
            "--skip-aws-check",
        ],
    )
    assert result_force.exit_code == 0
    assert load_workspace_config(workspace_dir).customer.name == "Example Customer"
