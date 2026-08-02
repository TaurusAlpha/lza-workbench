"""Tests for workspace paths derived from WorkspaceConfig."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.core.workspace import (
    WorkspaceConfig,
    WorkspaceState,
    create_workspace,
    planned_write_paths,
)


def test_workspace_paths_come_from_configuration(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspace"
    template_dir = tmp_path / "template"
    template_dir.mkdir()
    (template_dir / "global-config.yaml").write_text("{}\n", encoding="utf-8")
    config = WorkspaceConfig.model_validate(
        {
            "customer": {"name": "Example Customer", "slug": "example-customer"},
            "aws": {"profile": "example-root", "region": "eu-west-1"},
            "installer": {"local_path": "local/installer"},
            "configuration": {"local_path": "local/config"},
        }
    )

    create_workspace(
        workspace_dir=workspace_dir,
        template_config_dir=template_dir,
        config=config,
        state=WorkspaceState(),
    )

    assert (workspace_dir / "local/installer").is_dir()
    assert (workspace_dir / "local/config/global-config.yaml").is_file()
    assert not (workspace_dir / "aws-accelerator-installer").exists()
    assert not (workspace_dir / "aws-accelerator-config").exists()
    assert workspace_dir / "local/config" in planned_write_paths(workspace_dir, config)
    assert workspace_dir / "local/installer" in planned_write_paths(workspace_dir, config)
