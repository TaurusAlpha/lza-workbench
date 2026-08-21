"""Tests for Git configuration utilities and CodeCommit credential helper."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.configuration.git import (
    configure_codecommit_credential_helper,
    init_git_repository,
    is_git_repository,
)


def test_configure_codecommit_credential_helper(tmp_path: Path) -> None:
    repo_dir = tmp_path / "test-repo"
    init_git_repository(repo_dir)

    assert is_git_repository(repo_dir)

    configure_codecommit_credential_helper(repo_dir, "my-custom-profile")

    config_file = repo_dir / ".git" / "config"
    assert config_file.is_file()
    content = config_file.read_text(encoding="utf-8")

    assert "helper = !aws --profile my-custom-profile codecommit credential-helper $@" in content
    assert "UseHttpPath = true" in content


def test_init_git_repository_with_codecommit_profile(tmp_path: Path) -> None:
    repo_dir = tmp_path / "init-repo"
    remote_url = "https://git-codecommit.us-east-1.amazonaws.com/v1/repos/my-config-repo"

    init_git_repository(
        repo_dir,
        remote_name="origin",
        remote_url=remote_url,
        aws_profile="prod-admin",
    )

    config_file = repo_dir / ".git" / "config"
    assert config_file.is_file()
    content = config_file.read_text(encoding="utf-8")

    assert "helper = !aws --profile prod-admin codecommit credential-helper $@" in content
    assert "UseHttpPath = true" in content
