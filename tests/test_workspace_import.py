"""Tests for importing existing LZA configurations."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.commands.workspace_import import resolve_import_paths, run_import
from lza_workbench.core.templates import REQUIRED_TEMPLATE_FILES
from lza_workbench.core.workspace import load_workspace_config, load_workspace_state


def test_import_creates_metadata_without_modifying_configuration(tmp_path: Path) -> None:
    workspace_dir, config_dir = _make_configuration(tmp_path)
    config_file = config_dir / REQUIRED_TEMPLATE_FILES[0]
    content_before = config_file.read_text(encoding="utf-8")

    run_import(
        customer_name="Example Customer",
        workspace_dir=workspace_dir,
        config_dir=None,
        aws_profile="example-root",
        aws_region="eu-west-1",
        lza_version="v1.15.5",
        dry_run=False,
        force=False,
        skip_aws_check=True,
        interactive=False,
    )

    config = load_workspace_config(workspace_dir / "lza-workspace.yaml")
    assert config.configuration.local_path == "aws-accelerator-config"
    assert config.configuration.template.source == "local"
    assert load_workspace_state(workspace_dir / ".lza" / "state.json")
    assert config_file.read_text(encoding="utf-8") == content_before


def test_import_accepts_explicit_configuration_directory(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspace"
    config_dir = workspace_dir / "customer-config"
    _write_required_files(config_dir)

    resolved_workspace, resolved_config = resolve_import_paths(
        customer_name="Example Customer",
        workspace_dir=None,
        config_dir=config_dir,
        interactive=False,
    )

    assert resolved_workspace == workspace_dir
    assert resolved_config == config_dir


def test_import_dry_run_does_not_write_metadata(tmp_path: Path) -> None:
    workspace_dir, _ = _make_configuration(tmp_path)

    run_import(
        customer_name="Example Customer",
        workspace_dir=workspace_dir,
        config_dir=None,
        aws_profile="example-root",
        aws_region="eu-west-1",
        lza_version="v1.15.5",
        dry_run=True,
        force=False,
        skip_aws_check=True,
        interactive=False,
    )

    assert not (workspace_dir / "lza-workspace.yaml").exists()
    assert not (workspace_dir / ".lza").exists()


def _make_configuration(tmp_path: Path) -> tuple[Path, Path]:
    workspace_dir = tmp_path / "workspace"
    config_dir = workspace_dir / "aws-accelerator-config"
    _write_required_files(config_dir)
    return workspace_dir, config_dir


def _write_required_files(config_dir: Path) -> None:
    config_dir.mkdir(parents=True)
    for filename in REQUIRED_TEMPLATE_FILES:
        (config_dir / filename).write_text("{}\n", encoding="utf-8")
