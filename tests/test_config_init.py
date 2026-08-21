"""Tests for lza config init workflow and CLI command."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from lza_workbench.cli.main import app
from lza_workbench.configuration.rendering import (
    render_template_text,
    resolve_path_value,
)
from lza_workbench.configuration.templates import list_packaged_templates
from lza_workbench.errors import LzaError
from lza_workbench.workflows.config_init import (
    ConfigInitResult,
    init_config_workflow,
)
from lza_workbench.workflows.workspace_init import (
    build_workspace_config,
    init_workspace_workflow,
)
from lza_workbench.workspace.config import load_workspace_config, write_workspace_config

runner = CliRunner()


@pytest.fixture
def workspace_without_config(tmp_path: Path) -> Path:
    ws_dir = tmp_path / "test-workspace"
    init_workspace_workflow(
        customer_name="Test Customer",
        workspace_dir=ws_dir,
        aws_profile="test-root",
        aws_region="eu-west-1",
        skip_aws_check=True,
    )
    return ws_dir


def test_list_packaged_templates() -> None:
    templates = list_packaged_templates()
    assert "default" in templates


def test_resolve_path_value() -> None:
    config = build_workspace_config(
        customer_name="Acme Corp",
        customer_slug="acme-corp",
        aws_profile="acme-root",
        aws_region="eu-central-1",
        lza_version="v1.16.0",
    )
    config.installer.options.management_account_email = "mgmt@acme.com"

    assert resolve_path_value(config, "customer.slug") == "acme-corp"
    assert resolve_path_value(config, "config.customer.slug") == "acme-corp"
    assert (
        resolve_path_value(config, "installer.options.management_account_email") == "mgmt@acme.com"
    )
    assert resolve_path_value(config, "installer.options.log_archive_account_email") is None
    assert resolve_path_value(config, "nonexistent.field") is None


def test_placeholder_rendering_with_complete_config() -> None:
    config = build_workspace_config(
        customer_name="Acme Corp",
        customer_slug="acme-corp",
        aws_profile="acme-root",
        aws_region="eu-central-1",
        lza_version="v1.16.0",
    )
    config.installer.options.management_account_email = "mgmt@acme.com"
    config.installer.options.log_archive_account_email = "logs@acme.com"
    config.installer.options.audit_account_email = "audit@acme.com"

    sample_text = """
    customer: ${customer.slug}
    prefix: ${lza.accelerator_prefix}
    region: ${aws.region}
    homeRegion: '{{ HomeRegion }}'
    mgmt: ${installer.options.management_account_email}
    unknown: ${unknown.param}
    """

    rendered, unresolved = render_template_text(sample_text, config)

    assert "customer: acme-corp" in rendered
    assert "prefix: AWSAccelerator" in rendered
    assert "region: eu-central-1" in rendered
    assert "homeRegion: '{{ HomeRegion }}'" in rendered
    assert "mgmt: mgmt@acme.com" in rendered
    assert "unknown: ${unknown.param}" in rendered
    assert "${unknown.param}" in unresolved


def test_placeholder_rendering_with_unresolved_emails() -> None:
    config = build_workspace_config(
        customer_name="Acme Corp",
        customer_slug="acme-corp",
        aws_profile="acme-root",
        aws_region="eu-central-1",
    )

    sample_text = """
    mgmt: ${installer.options.management_account_email}
    logs: ${installer.options.log_archive_account_email}
    audit: ${installer.options.audit_account_email}
    home: '{{ HomeRegion }}'
    """

    rendered, unresolved = render_template_text(sample_text, config)

    assert "mgmt: ${installer.options.management_account_email}" in rendered
    assert "logs: ${installer.options.log_archive_account_email}" in rendered
    assert "audit: ${installer.options.audit_account_email}" in rendered
    assert "home: '{{ HomeRegion }}'" in rendered
    assert len(unresolved) == 3
    assert "${installer.options.management_account_email}" in unresolved


def test_config_init_workflow_dry_run(workspace_without_config: Path) -> None:
    result = init_config_workflow(
        target_dir=workspace_without_config,
        template_name="default",
        dry_run=True,
    )
    assert isinstance(result, ConfigInitResult)
    assert result.dry_run is True
    assert not (workspace_without_config / "aws-accelerator-config").exists()
    assert len(result.written_paths) > 0
    # Because installer emails were not set, unresolved placeholders should be reported
    assert len(result.unresolved_placeholders) > 0


def test_config_init_workflow_execution(workspace_without_config: Path) -> None:
    # Set installer emails in workspace config
    cfg = load_workspace_config(workspace_without_config)
    cfg.installer.options.management_account_email = "mgmt@example.com"
    cfg.installer.options.log_archive_account_email = "logs@example.com"
    cfg.installer.options.audit_account_email = "audit@example.com"
    write_workspace_config(workspace_without_config, cfg)

    result = init_config_workflow(
        target_dir=workspace_without_config,
        template_name="default",
        dry_run=False,
    )
    assert isinstance(result, ConfigInitResult)
    assert result.dry_run is False
    assert (workspace_without_config / "aws-accelerator-config").is_dir()
    assert (workspace_without_config / "aws-accelerator-config" / "global-config.yaml").is_file()

    accounts_yaml = (
        workspace_without_config / "aws-accelerator-config" / "accounts-config.yaml"
    ).read_text(encoding="utf-8")
    assert "mgmt@example.com" in accounts_yaml
    assert "logs@example.com" in accounts_yaml
    assert "audit@example.com" in accounts_yaml
    assert "${" not in accounts_yaml

    # No unresolved placeholders
    assert len(result.unresolved_placeholders) == 0


def test_config_init_workflow_refuses_overwrite_without_force(
    workspace_without_config: Path,
) -> None:
    # First init
    init_config_workflow(
        target_dir=workspace_without_config,
        template_name="default",
        dry_run=False,
    )

    # Second init without force
    with pytest.raises(LzaError, match=r"Configuration directory already exists.*--force"):
        init_config_workflow(
            target_dir=workspace_without_config,
            template_name="default",
            force=False,
            dry_run=False,
        )


def test_config_init_workflow_with_force_cleans_and_repopulates(
    workspace_without_config: Path,
) -> None:
    config_dir = workspace_without_config / "aws-accelerator-config"
    init_config_workflow(
        target_dir=workspace_without_config,
        template_name="default",
        dry_run=False,
    )

    # Add an obsolete test file
    obsolete_file = config_dir / "obsolete-file.txt"
    obsolete_file.write_text("old content", encoding="utf-8")
    assert obsolete_file.exists()

    # Re-run with force
    init_config_workflow(
        target_dir=workspace_without_config,
        template_name="default",
        force=True,
        dry_run=False,
    )

    assert config_dir.is_dir()
    assert not obsolete_file.exists()
    assert (config_dir / "global-config.yaml").is_file()


def test_config_init_cli_dry_run(
    workspace_without_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(workspace_without_config)

    res = runner.invoke(app, ["config", "init", "--dry-run"])
    assert res.exit_code == 0
    assert "Dry run: lza config init" in res.output
    assert "Planned writes:" in res.output
    assert not (workspace_without_config / "aws-accelerator-config").exists()


def test_config_init_cli_execution(
    workspace_without_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(workspace_without_config)

    res = runner.invoke(app, ["config", "init"])
    assert res.exit_code == 0
    assert "Initialized LZA configuration" in res.output
    assert (workspace_without_config / "aws-accelerator-config").is_dir()


def test_config_init_cli_force(
    workspace_without_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(workspace_without_config)

    # First init
    runner.invoke(app, ["config", "init"])

    # Second without force fails
    res = runner.invoke(app, ["config", "init"])
    assert res.exit_code == 1

    # Second with force succeeds
    res_force = runner.invoke(app, ["config", "init", "--force"])
    assert res_force.exit_code == 0
    assert "Initialized LZA configuration" in res_force.output
