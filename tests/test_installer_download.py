"""Tests for downloading and configuring LZA CloudFormation installer template."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer

from lza_workbench.commands.installer_download import (
    normalize_lza_version,
    resolve_template_url,
    run_download_installer,
)
from lza_workbench.commands.workspace_init import run_init
from lza_workbench.core.installer_template import (
    configure_anonymous_data,
    resolve_installer_template,
)
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
        Path(__file__).parents[1] / "src" / "lza_workbench" / "config" / "examples" / "full.yaml"
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
                "SolutionHelperAnonymousData14B64A81": {"SendAnonymizedData": {"Data": "Yes"}}
            }
        }
    )

    disabled = configure_anonymous_data(sample_json, enable=False)
    data_disabled = json.loads(disabled)
    assert (
        data_disabled["Mappings"]["SolutionHelperAnonymousData14B64A81"]["SendAnonymizedData"][
            "Data"
        ]
        == "No"
    )

    enabled = configure_anonymous_data(sample_json, enable=True)
    data_enabled = json.loads(enabled)
    assert (
        data_enabled["Mappings"]["SolutionHelperAnonymousData14B64A81"]["SendAnonymizedData"][
            "Data"
        ]
        == "Yes"
    )


def test_configure_anonymous_data_invalid_json() -> None:
    """Test that invalid JSON is returned unchanged."""
    invalid_content = "not valid json {{{"
    result = configure_anonymous_data(invalid_content, enable=True)
    assert result == invalid_content


def test_resolve_installer_template_remote_success() -> None:
    """Test successful remote download of installer template."""
    url = (
        "https://s3.amazonaws.com/solutions-reference/"
        "landing-zone-accelerator-on-aws/v1.16.0/AWSAccelerator-InstallerStack.template"
    )

    class MockResponse:
        def __enter__(self) -> MockResponse:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def read(self) -> bytes:
            return b"mock template content"

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(
            "urllib.request.urlopen",
            lambda req, *args, **kwargs: MockResponse(),
        )

        result = resolve_installer_template(url)
        assert "mock template content" in result


def test_resolve_installer_template_remote_failure_with_fallback() -> None:
    """Test fallback to packaged template when remote download fails."""
    url = (
        "https://s3.amazonaws.com/solutions-reference/"
        "landing-zone-accelerator-on-aws/v1.16.0/AWSAccelerator-InstallerStack.template"
    )

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(
            "urllib.request.urlopen",
            lambda req, *args, **kwargs: (_ for _ in []).throw(Exception("Network error")),
        )

        result = resolve_installer_template(url, fallback_version="v1.16.0")
        assert result is not None
        assert len(result) > 0


def test_resolve_installer_template_remote_failure_no_fallback() -> None:
    """Test that BadParameter is raised when remote download fails and no fallback exists."""
    url = (
        "https://s3.amazonaws.com/solutions-reference/"
        "landing-zone-accelerator-on-aws/v1.16.0/AWSAccelerator-InstallerStack.template"
    )

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(
            "urllib.request.urlopen",
            lambda req, *args, **kwargs: (_ for _ in []).throw(Exception("Network error")),
        )

        with pytest.raises(typer.BadParameter, match="Unable to download installer template"):
            resolve_installer_template(url, fallback_version=None)


def test_resolve_installer_template_invalid_url() -> None:
    """Test that invalid URLs are handled gracefully."""
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(
            "urllib.request.urlopen",
            lambda req, *args, **kwargs: (_ for _ in []).throw(Exception("Invalid URL")),
        )

        with pytest.raises(typer.BadParameter, match="Unable to download installer template"):
            resolve_installer_template("http://invalid-url.com/template", fallback_version=None)


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
        lza_version="v1.16.0",
        force=False,
    )
    assert dest is not None
    state = load_workspace_state(ws_dir / WORKSPACE_STATE_FILE)
    assert state.installer_downloaded_at is None
