"""Tests for downloading and configuring LZA CloudFormation installer template."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer

from lza_workbench.commands.download_installer import (
    _configure_anonymous_data,
    normalize_lza_version,
    resolve_template_url,
    run_download_installer,
)
from lza_workbench.commands.init_workspace import run_init
from lza_workbench.core.workspace import (
    WORKSPACE_STATE_FILE,
    build_installer_cfn_parameters,
    load_workspace_config,
    load_workspace_state,
)


def test_normalize_lza_version() -> None:
    assert normalize_lza_version("v1.16.0") == "v1.16.0"
    assert normalize_lza_version("1.16.0") == "v1.16.0"
    assert normalize_lza_version("latest") == "latest"
    assert normalize_lza_version("") == "latest"


def test_resolve_template_url() -> None:
    url_versioned = resolve_template_url("v1.16.0")
    assert "v1.16.0/AWSAccelerator-InstallerStack.template" in url_versioned

    url_latest = resolve_template_url("latest")
    assert "latest/AWSAccelerator-InstallerStack.template" in url_latest


def test_build_installer_cfn_parameters() -> None:
    config_path = (
        Path(__file__).parents[1]
        / "src"
        / "lza_workbench"
        / "config"
        / "examples"
        / "full.yaml"
    )
    config = load_workspace_config(config_path)
    cfn_params = build_installer_cfn_parameters(config)

    assert cfn_params["RepositorySource"] == "github"
    assert cfn_params["RepositoryOwner"] == "awslabs"
    assert cfn_params["RepositoryName"] == "landing-zone-accelerator-on-aws"
    assert cfn_params["EnableApprovalStage"] == "No"
    assert cfn_params["ControlTowerEnabled"] == "Yes"
    assert cfn_params["AcceleratorPrefix"] == "AWSAccelerator"
    assert cfn_params["ConfigurationRepositoryLocation"] == "s3"


def test_configure_anonymous_data() -> None:
    sample_json = json.dumps(
        {
            "Mappings": {
                "SolutionHelperAnonymousData14B64A81": {
                    "SendAnonymizedData": {"Data": "Yes"}
                }
            }
        }
    )

    disabled = _configure_anonymous_data(sample_json, enable=False)
    data_disabled = json.loads(disabled)
    assert (
        data_disabled["Mappings"]["SolutionHelperAnonymousData14B64A81"]["SendAnonymizedData"][
            "Data"
        ]
        == "No"
    )

    enabled = _configure_anonymous_data(sample_json, enable=True)
    data_enabled = json.loads(enabled)
    assert (
        data_enabled["Mappings"]["SolutionHelperAnonymousData14B64A81"]["SendAnonymizedData"][
            "Data"
        ]
        == "Yes"
    )


def test_download_installer_dry_run(tmp_path: Path) -> None:
    ws_dir = tmp_path / "test-customer"
    run_init(
        customer_name="Test Customer",
        workspace_dir=ws_dir,
        aws_profile="default",
        aws_region="us-east-1",
        lza_version="v1.16.0",
        dry_run=False,
        force=False,
        skip_aws_check=True,
        interactive=False,
    )

    dest = run_download_installer(
        dry_run=True,
        target_dir=ws_dir,
    )
    assert dest == ws_dir / "aws-accelerator-installer" / "AWSAccelerator-InstallerStack.template"
    assert not dest.exists()


def test_download_installer_executes_and_updates_state(tmp_path: Path) -> None:
    ws_dir = tmp_path / "test-customer"
    run_init(
        customer_name="Test Customer",
        workspace_dir=ws_dir,
        aws_profile="default",
        aws_region="us-east-1",
        lza_version="v1.16.0",
        dry_run=False,
        force=False,
        skip_aws_check=True,
        interactive=False,
    )

    dest = run_download_installer(
        lza_version="v1.16.0",
        force=True,
        target_dir=ws_dir,
    )

    assert dest.exists()
    content = dest.read_text(encoding="utf-8")
    assert "Description" in content

    # Check state file
    state = load_workspace_state(ws_dir / WORKSPACE_STATE_FILE)
    assert state.installer_downloaded_at is not None
    assert state.installer_template_version == "v1.16.0"

    # Re-running without force should raise BadParameter
    with pytest.raises(typer.BadParameter, match="already exists"):
        run_download_installer(
            lza_version="v1.16.0",
            force=False,
            target_dir=ws_dir,
        )
