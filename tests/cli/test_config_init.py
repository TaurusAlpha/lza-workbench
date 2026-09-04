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
from lza_workbench.workflows.config_init import (
    ConfigInitResult,
    init_config_workflow,
)
from lza_workbench.workflows.workspace_init import (
    build_workspace_config,
    init_workspace_workflow,
)
from lza_workbench.workspace.config import load_workspace_config, write_workspace_config
from lza_workbench.workspace.state import load_workspace_state

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
    assert len(result.unresolved_placeholders) > 0


def test_config_init_workflow_execution(workspace_without_config: Path) -> None:
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

    assert len(result.unresolved_placeholders) == 0

    state = load_workspace_state(workspace_without_config)
    assert state.config_initialized_at is not None
    assert state.config_template_name == "default"
    assert state.config_template_source == "packaged"
    mgmt_key = "installer.options.management_account_email"
    assert state.config_init_values is not None
    assert state.config_init_values.get(mgmt_key) == "mgmt@example.com"
    assert state.config_init_digest is not None
    assert state.config_files_count == 8


def test_config_init_workflow_skips_when_unmanaged(
    workspace_without_config: Path,
) -> None:
    config_dir = workspace_without_config / "aws-accelerator-config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "manual-config.yaml").write_text("dummy", encoding="utf-8")

    result = init_config_workflow(
        target_dir=workspace_without_config,
        template_name="default",
        force=False,
        dry_run=False,
    )
    assert result.skipped is True
    assert result.is_managed is False


def test_config_init_workflow_skips_when_already_initialized(
    workspace_without_config: Path,
) -> None:
    first_res = init_config_workflow(
        target_dir=workspace_without_config,
        template_name="default",
        dry_run=False,
    )
    assert first_res.skipped is False

    second_res = init_config_workflow(
        target_dir=workspace_without_config,
        template_name="default",
        force=False,
        dry_run=False,
    )
    assert second_res.skipped is True
    assert second_res.is_managed is True
    assert second_res.initialized_at is not None
    assert len(second_res.drifted_fields) == 0


def test_config_init_workflow_detects_drift_on_existing_dir(
    workspace_without_config: Path,
) -> None:
    init_config_workflow(
        target_dir=workspace_without_config,
        template_name="default",
        dry_run=False,
    )

    # Now update installer options in workspace config
    cfg = load_workspace_config(workspace_without_config)
    cfg.installer.options.management_account_email = "newmgmt@example.com"
    write_workspace_config(workspace_without_config, cfg)

    result = init_config_workflow(
        target_dir=workspace_without_config,
        template_name="default",
        force=False,
        dry_run=False,
    )
    assert result.skipped is True
    assert result.is_managed is True
    assert "installer.options.management_account_email" in result.drifted_fields


def test_config_init_workflow_with_force_cleans_and_repopulates(
    workspace_without_config: Path,
) -> None:
    config_dir = workspace_without_config / "aws-accelerator-config"
    init_config_workflow(
        target_dir=workspace_without_config,
        template_name="default",
        dry_run=False,
    )

    obsolete_file = config_dir / "obsolete-file.txt"
    obsolete_file.write_text("old content", encoding="utf-8")
    assert obsolete_file.exists()

    result = init_config_workflow(
        target_dir=workspace_without_config,
        template_name="default",
        force=True,
        dry_run=False,
    )
    assert result.skipped is False
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


def test_config_init_cli_existing_notice_and_force(
    workspace_without_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(workspace_without_config)

    runner.invoke(app, ["config", "init"])

    # Second invocation without force displays informational notice, exit code 0
    res = runner.invoke(app, ["config", "init"])
    assert res.exit_code == 0
    assert "already exists" in res.output

    # Force re-initializes
    res_force = runner.invoke(app, ["config", "init", "--force"])
    assert res_force.exit_code == 0
    assert "Initialized LZA configuration" in res_force.output


def test_config_init_cli_single_template_no_prompt(
    workspace_without_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(workspace_without_config)
    monkeypatch.setattr(
        "lza_workbench.cli.commands.config_init.list_packaged_templates",
        lambda: ["default"],
    )

    res = runner.invoke(app, ["config", "init"])
    assert res.exit_code == 0
    assert "Available configuration templates" not in res.output
    assert "Initialized LZA configuration" in res.output


def test_config_init_cli_multiple_templates_explicit_flag(
    workspace_without_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(workspace_without_config)
    monkeypatch.setattr(
        "lza_workbench.cli.commands.config_init.list_packaged_templates",
        lambda: ["default", "custom-corp"],
    )

    res = runner.invoke(app, ["config", "init", "--template", "default"])
    assert res.exit_code == 0
    assert "Available configuration templates" not in res.output
    assert "Template: default" in res.output


def test_config_init_cli_multiple_templates_prompt_selection(
    workspace_without_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(workspace_without_config)
    monkeypatch.setattr(
        "lza_workbench.cli.commands.config_init.list_packaged_templates",
        lambda: ["default", "enterprise"],
    )

    # Simulate user entering 2 (or enterprise) when prompted
    called_template: list[str] = []

    def mock_init(*args: object, **kwargs: object) -> ConfigInitResult:
        called_template.append(str(kwargs.get("template_name")))
        from lza_workbench.configuration.templates import resolve_template_source

        cfg = load_workspace_config(workspace_without_config)
        return ConfigInitResult(
            workspace_dir=workspace_without_config,
            config_dir=workspace_without_config / "aws-accelerator-config",
            template_source=resolve_template_source("default"),
            written_paths=[],
            unresolved_placeholders=[],
            dry_run=False,
            config=cfg,
        )

    monkeypatch.setattr("lza_workbench.cli.commands.config_init.init_config_workflow", mock_init)

    res = runner.invoke(app, ["config", "init"], input="2\n")
    assert res.exit_code == 0
    assert "Available configuration templates:" in res.output
    assert "1. default" in res.output
    assert "2. enterprise" in res.output
    assert called_template == ["enterprise"]


def test_config_init_s3_initializes_git_repo_and_commits(
    workspace_without_config: Path,
) -> None:
    cfg = load_workspace_config(workspace_without_config)
    cfg.configuration.repository.type = "s3"
    write_workspace_config(workspace_without_config, cfg)

    result = init_config_workflow(
        target_dir=workspace_without_config,
        template_name="default",
        dry_run=False,
    )

    assert result.git_initialized is True
    assert result.git_committed is True
    assert result.git_skipped is False
    assert result.git_skip_reason is None

    config_dir = workspace_without_config / "aws-accelerator-config"
    assert (config_dir / ".git").is_dir()
    from lza_workbench.configuration.git import get_git_commit, has_commits

    assert has_commits(config_dir) is True
    assert get_git_commit(config_dir) != ""


def test_config_init_s3_dry_run_does_not_mutate_git(
    workspace_without_config: Path,
) -> None:
    cfg = load_workspace_config(workspace_without_config)
    cfg.configuration.repository.type = "s3"
    write_workspace_config(workspace_without_config, cfg)

    result = init_config_workflow(
        target_dir=workspace_without_config,
        template_name="default",
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.git_initialized is False
    assert result.git_committed is False
    config_dir = workspace_without_config / "aws-accelerator-config"
    assert not (config_dir / ".git").exists()


def test_config_init_s3_skips_when_directory_already_has_git(
    workspace_without_config: Path,
) -> None:
    cfg = load_workspace_config(workspace_without_config)
    cfg.configuration.repository.type = "s3"
    write_workspace_config(workspace_without_config, cfg)

    config_dir = workspace_without_config / "aws-accelerator-config"
    config_dir.mkdir(parents=True, exist_ok=True)
    from lza_workbench.configuration.git import init_git_repository

    init_git_repository(config_dir)
    assert (config_dir / ".git").is_dir()

    # Re-run with force to populate into existing git repo
    result = init_config_workflow(
        target_dir=workspace_without_config,
        template_name="default",
        force=True,
        dry_run=False,
    )

    assert result.git_initialized is False
    assert result.git_committed is False
    assert result.git_skipped is True
    assert result.git_skip_reason == "Directory already has a Git repository"
    assert (config_dir / ".git").is_dir()


def test_config_init_s3_skips_when_inside_parent_git_repo(
    workspace_without_config: Path,
) -> None:
    cfg = load_workspace_config(workspace_without_config)
    cfg.configuration.repository.type = "s3"
    write_workspace_config(workspace_without_config, cfg)

    # Initialize git in workspace root (parent)
    from lza_workbench.configuration.git import init_git_repository

    init_git_repository(workspace_without_config)
    assert (workspace_without_config / ".git").is_dir()

    result = init_config_workflow(
        target_dir=workspace_without_config,
        template_name="default",
        dry_run=False,
    )

    assert result.git_initialized is False
    assert result.git_committed is False
    assert result.git_skipped is True
    assert result.git_skip_reason == "Directory is inside an existing parent Git repository"

    config_dir = workspace_without_config / "aws-accelerator-config"
    assert not (config_dir / ".git").exists()


def test_config_init_non_s3_skips_git_init(
    workspace_without_config: Path,
) -> None:
    cfg = load_workspace_config(workspace_without_config)
    cfg.configuration.repository.type = "codecommit"
    write_workspace_config(workspace_without_config, cfg)

    result = init_config_workflow(
        target_dir=workspace_without_config,
        template_name="default",
        dry_run=False,
    )

    assert result.git_initialized is False
    assert result.git_committed is False
    assert result.git_skipped is True
    assert "Remote configuration repository is 'codecommit'" in (result.git_skip_reason or "")

    config_dir = workspace_without_config / "aws-accelerator-config"
    assert not (config_dir / ".git").exists()


def test_config_init_preserves_existing_git_on_force(
    workspace_without_config: Path,
) -> None:
    cfg = load_workspace_config(workspace_without_config)
    cfg.configuration.repository.type = "s3"
    write_workspace_config(workspace_without_config, cfg)

    # First init creates Git repo and initial commit
    first_res = init_config_workflow(
        target_dir=workspace_without_config,
        template_name="default",
        dry_run=False,
    )
    assert first_res.git_initialized is True

    config_dir = workspace_without_config / "aws-accelerator-config"
    assert (config_dir / ".git").is_dir()
    from lza_workbench.configuration.git import get_git_commit

    initial_commit = get_git_commit(config_dir)

    # Re-init with --force
    force_res = init_config_workflow(
        target_dir=workspace_without_config,
        template_name="default",
        force=True,
        dry_run=False,
    )

    assert force_res.git_skipped is True
    assert (config_dir / ".git").is_dir()
    assert get_git_commit(config_dir) == initial_commit


def test_config_init_git_failure_surfaces_clean_error(
    workspace_without_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lza_workbench.errors import LzaError

    cfg = load_workspace_config(workspace_without_config)
    cfg.configuration.repository.type = "s3"
    write_workspace_config(workspace_without_config, cfg)

    def mock_fail(repo_dir: Path) -> None:
        raise LzaError("Simulated git initialization failure")

    monkeypatch.setattr("lza_workbench.workflows.config_init.init_git_repository", mock_fail)

    with pytest.raises(LzaError, match="Simulated git initialization failure"):
        init_config_workflow(
            target_dir=workspace_without_config,
            template_name="default",
            dry_run=False,
        )
