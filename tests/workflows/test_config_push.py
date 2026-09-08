"""Workflow-level tests for configuration Git pushes."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from lza_workbench.errors import LzaError
from lza_workbench.workflows.config_push import (
    ConfigPushRequest,
    apply_config_push,
    push_configuration_workflow,
)
from lza_workbench.workspace.config import load_workspace_config, write_workspace_config
from lza_workbench.workspace.state import load_workspace_state


def _configure_codecommit_workspace(workspace_dir: Path, *, branch: str = "main") -> Path:
    config = load_workspace_config(workspace_dir)
    config.configuration.repository.type = "codecommit"
    config.configuration.repository.repository_name = "deployable-config"
    config.configuration.repository.branch = branch
    write_workspace_config(workspace_dir, config)
    return workspace_dir / config.configuration.local_path


def test_git_push_dry_run_does_not_add_remote_or_credential_helper(
    configured_workspace: Path,
    init_git_repo,
) -> None:
    config_dir = _configure_codecommit_workspace(configured_workspace)
    init_git_repo(config_dir)

    result = push_configuration_workflow(target_dir=configured_workspace, dry_run=True)

    assert result.dry_run is True
    assert result.git_remote_url == (
        "https://git-codecommit.eu-west-1.amazonaws.com/v1/repos/deployable-config"
    )
    git_config = (config_dir / ".git" / "config").read_text(encoding="utf-8")
    assert '[remote "origin"]' not in git_config
    assert "credential-helper" not in git_config


def test_git_push_rejects_remote_that_differs_from_workspace_configuration(
    configured_workspace: Path,
    init_git_repo,
) -> None:
    config_dir = _configure_codecommit_workspace(configured_workspace)
    init_git_repo(config_dir)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://example.invalid/wrong-repository.git"],
        cwd=config_dir,
        check=True,
        capture_output=True,
    )

    with pytest.raises(LzaError, match="does not match lza-workspace.yaml"):
        push_configuration_workflow(target_dir=configured_workspace, dry_run=True)


def test_git_push_rejects_non_deployable_current_branch(
    configured_workspace: Path,
    init_git_repo,
) -> None:
    config_dir = _configure_codecommit_workspace(configured_workspace, branch="deployable")
    init_git_repo(config_dir)

    with pytest.raises(LzaError, match="not the configured deployable branch"):
        push_configuration_workflow(target_dir=configured_workspace, dry_run=True)


def test_git_push_updates_remote_and_state_for_configured_deployable_branch(
    configured_workspace: Path,
    init_git_repo,
    tmp_path: Path,
) -> None:
    config_dir = configured_workspace / "aws-accelerator-config"
    init_git_repo(config_dir)
    remote_dir = tmp_path / "configuration-remote.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote_dir)],
        check=True,
        capture_output=True,
    )

    config = load_workspace_config(configured_workspace)
    config.configuration.repository.type = "codeconnection"
    config.configuration.repository.codeconnection_arn = (
        "arn:aws:codeconnections:eu-west-1:123456789012:connection/example"
    )
    config.configuration.repository.owner = "example"
    config.configuration.repository.repository_name = "configuration"
    config.configuration.repository.branch = "main"
    write_workspace_config(configured_workspace, config)
    subprocess.run(
        ["git", "remote", "add", "origin", str(remote_dir)],
        cwd=config_dir,
        check=True,
        capture_output=True,
    )

    result = push_configuration_workflow(target_dir=configured_workspace)

    remote_commit = subprocess.run(
        ["git", "--git-dir", str(remote_dir), "rev-parse", "--short", "main"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    state = load_workspace_state(configured_workspace)
    assert remote_commit == result.git_commit
    assert state.config_artifact_sha256 == remote_commit


@pytest.mark.parametrize("dry_run", [False, True])
def test_imported_s3_push_without_sync_is_protected(
    configured_workspace,
    mock_aws_execution_context,
    dry_run,
):
    from lza_workbench.workspace.state import write_workspace_state

    state = load_workspace_state(configured_workspace)
    state.imported = True
    write_workspace_state(configured_workspace, state)
    config = load_workspace_config(configured_workspace)
    config.configuration.repository.bucket = None
    write_workspace_config(configured_workspace, config)
    before = {
        p.relative_to(configured_workspace): p.read_bytes()
        for p in configured_workspace.rglob("*")
        if p.is_file()
    }
    if dry_run:
        result = push_configuration_workflow(
            target_dir=configured_workspace,
            dry_run=True,
            aws_context=mock_aws_execution_context,
        )
        assert result.safety_warning is not None
        assert "has not been verified" in result.safety_warning
        assert result.s3_bucket == "aws-accelerator-config-123456789012-eu-west-1"
    else:
        with pytest.raises(LzaError, match="lza config download.*--force"):
            push_configuration_workflow(
                target_dir=configured_workspace,
                aws_context=mock_aws_execution_context,
            )
    after = {
        p.relative_to(configured_workspace): p.read_bytes()
        for p in configured_workspace.rglob("*")
        if p.is_file()
    }
    assert before == after
    mock_aws_execution_context.factory.get_client.assert_not_called()


@pytest.mark.parametrize("override", ["force", "confirm", "decline"])
def test_imported_s3_push_overrides(configured_workspace, mock_aws_execution_context, override):
    from lza_workbench.workspace.state import write_workspace_state

    state = load_workspace_state(configured_workspace)
    state.imported = True
    write_workspace_state(configured_workspace, state)
    request = ConfigPushRequest(
        target_dir=configured_workspace,
        aws_context=mock_aws_execution_context,
        force=override == "force",
        overwrite_confirmed=override == "confirm",
    )
    mock_aws_execution_context.factory.get_client.return_value.head_object.return_value = {}
    if override == "decline":
        with pytest.raises(LzaError, match="has not been verified"):
            apply_config_push(request)
        mock_aws_execution_context.factory.get_client.assert_not_called()
    else:
        apply_config_push(request)
        assert load_workspace_state(configured_workspace).config_sync_digest
        mock_aws_execution_context.factory.get_client.return_value.upload_file.assert_called_once()
