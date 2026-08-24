"""Central test fixtures for LZA Workbench test suite."""

from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from lza_workbench.aws.context import AwsExecutionContext
from lza_workbench.installer.versions import PACKAGED_INSTALLER_VERSION
from lza_workbench.workflows.config_init import init_config_workflow
from lza_workbench.workflows.workspace_init import init_workspace_workflow
from lza_workbench.workspace.config import load_workspace_config, write_workspace_config
from lza_workbench.workspace.schema import (
    AwsConfig,
    CustomerConfig,
    LzaConfig,
    WorkspaceConfig,
    WorkspaceState,
)
from lza_workbench.workspace.state import write_workspace_state


@pytest.fixture
def cli_runner() -> CliRunner:
    """Fixture providing an isolated Typer CLI runner."""
    return CliRunner()


@pytest.fixture
def sample_aws_identity() -> dict[str, str]:
    """Sample AWS caller identity dictionary."""
    return {
        "account": "123456789012",
        "arn": "arn:aws:iam::123456789012:user/admin",
        "user_id": "ADMIN123",
    }


@pytest.fixture
def mock_aws_execution_context(sample_aws_identity: dict[str, str]) -> AwsExecutionContext:
    """Mock AWS execution context with valid identity."""
    return AwsExecutionContext(
        region="us-east-1",
        factory=MagicMock(),
        identity=sample_aws_identity,
        error=None,
    )


@pytest.fixture
def sample_workspace_config() -> WorkspaceConfig:
    """Sample standard workspace configuration object."""
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Acme Corp", slug="acme-corp"),
        aws=AwsConfig(profile="acme-root", region="eu-west-1"),
        assets_bucket="s3-lza-workbench-assets-123456789012-eu-west-1",
        lza=LzaConfig(version=PACKAGED_INSTALLER_VERSION, accelerator_prefix="AWSAccelerator"),
    )
    config.installer.source_code.repository_type = "codecommit"
    config.installer.source_code.repository_name = "aws-accelerator-codecommit"
    config.installer.source_code.branch = f"release/{PACKAGED_INSTALLER_VERSION}"
    config.installer.options.management_account_email = "root@example.com"
    config.installer.options.log_archive_account_email = "log@example.com"
    config.installer.options.audit_account_email = "audit@example.com"
    return config


@pytest.fixture
def initialized_workspace(tmp_path: Path) -> Path:
    """Create a temporary initialized workspace directory."""
    ws_dir = tmp_path / "initialized-workspace"
    init_workspace_workflow(
        customer_name="Acme Corp",
        workspace_dir=ws_dir,
        aws_profile="acme-root",
        aws_region="eu-west-1",
        lza_version=PACKAGED_INSTALLER_VERSION,
        skip_aws_check=True,
        dry_run=False,
        force=False,
    )
    return ws_dir


@pytest.fixture
def imported_workspace(tmp_path: Path) -> Path:
    """Create a temporary imported workspace directory."""
    import shutil

    from lza_workbench.configuration.templates import resolve_template_source
    from lza_workbench.workflows.workspace_import import import_workspace_workflow

    ws_dir = tmp_path / "imported-workspace"
    config_dir = ws_dir / "aws-accelerator-config"
    config_dir.mkdir(parents=True)
    template = resolve_template_source("default")
    for f in template.config_dir.glob("*.yaml"):
        shutil.copy(f, config_dir / f.name)

    import_workspace_workflow(
        workspace_dir=ws_dir,
        customer_name="Acme Corp",
        aws_profile="acme-root",
        aws_region="eu-west-1",
        lza_version=PACKAGED_INSTALLER_VERSION,
        dry_run=False,
        skip_aws_check=True,
    )
    return ws_dir


@pytest.fixture
def configured_workspace(tmp_path: Path) -> Path:
    """Create a fully configured workspace with configuration and installer setup."""
    ws_dir = tmp_path / "configured-workspace"
    init_workspace_workflow(
        customer_name="Acme Corp",
        workspace_dir=ws_dir,
        aws_profile="acme-root",
        aws_region="eu-west-1",
        lza_version=PACKAGED_INSTALLER_VERSION,
        skip_aws_check=True,
        dry_run=False,
        force=False,
    )
    init_config_workflow(target_dir=ws_dir)

    config = load_workspace_config(ws_dir)
    config.assets_bucket = "s3-lza-workbench-assets-123456789012-eu-west-1"
    config.configuration.repository.type = "s3"
    config.configuration.repository.bucket = "test-config-bucket"
    config.installer.source_code.repository_type = "codecommit"
    config.installer.source_code.repository_name = "aws-accelerator-codecommit"
    config.installer.source_code.branch = f"release/{PACKAGED_INSTALLER_VERSION}"
    config.installer.options.management_account_email = "mgmt@example.com"
    config.installer.options.log_archive_account_email = "log@example.com"
    config.installer.options.audit_account_email = "audit@example.com"

    write_workspace_config(ws_dir, config)
    write_workspace_state(ws_dir, WorkspaceState.from_config(config))

    # Add mock installer stack template
    installer_dir = ws_dir / "aws-accelerator-installer"
    installer_dir.mkdir(parents=True, exist_ok=True)
    template_file = installer_dir / "AWSAccelerator-InstallerStack.template"
    template_file.write_text(
        '{"Description": "Installer", "Parameters": {'
        '"ManagementAccountEmail": {"Type": "String", "Description": "Email"},'
        '"RepositorySource": {"Type": "String", "AllowedValues": ["github", "codecommit"]}'
        "}}",
        encoding="utf-8",
    )
    return ws_dir


def init_test_git_repo(config_dir: Path, commit: bool = True) -> None:
    """Initialize a local Git repository in config_dir with initial commit."""
    subprocess.run(["git", "init", "-b", "main"], cwd=config_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "LZA Tester"],
        cwd=config_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "tester@example.com"],
        cwd=config_dir,
        check=True,
        capture_output=True,
    )
    if commit:
        subprocess.run(["git", "add", "."], cwd=config_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial LZA configuration"],
            cwd=config_dir,
            check=True,
            capture_output=True,
        )


def create_sample_config_zip(
    destination_path: Path, files_content: dict[str, str] | None = None
) -> Path:
    """Create a sample configuration zip archive for download/upload tests."""
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    contents = files_content or {
        "aws-accelerator-config/global-config.yaml": "global: content",
        "aws-accelerator-config/organization-config.yaml": "org: content",
        "aws-accelerator-config/accounts-config.yaml": "accounts: content",
        "aws-accelerator-config/network-config.yaml": "network: content",
        "aws-accelerator-config/security-config.yaml": "security: content",
        "aws-accelerator-config/iam-config.yaml": "iam: content",
    }
    with zipfile.ZipFile(destination_path, "w") as zf:
        for path_in_zip, text in contents.items():
            zf.writestr(path_in_zip, text)
    return destination_path


@pytest.fixture
def init_git_repo() -> Any:
    """Fixture providing helper to initialize a Git repository."""
    return init_test_git_repo


@pytest.fixture
def sample_config_zip() -> Any:
    """Fixture providing helper to generate a sample configuration zip archive."""
    return create_sample_config_zip

