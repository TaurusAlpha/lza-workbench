"""Tests for workspace paths derived from WorkspaceConfig."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.workspace.schema import (
    WorkspaceConfig,
    WorkspaceState,
)
from lza_workbench.workspace.setup import (
    create_workspace,
    planned_write_paths,
)


def test_workspace_paths_come_from_configuration(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspace"
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
        config=config,
        state=WorkspaceState(),
    )

    assert (workspace_dir / "local/installer").is_dir()
    assert not (workspace_dir / "local/config").exists()
    assert not (workspace_dir / "aws-accelerator-installer").exists()
    assert not (workspace_dir / "aws-accelerator-config").exists()
    assert workspace_dir / "local/installer" in planned_write_paths(workspace_dir, config)
