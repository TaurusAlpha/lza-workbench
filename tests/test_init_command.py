from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer

from lza_workbench.commands.init import collect_init_request, run_init
from lza_workbench.core.project import InitRequest
from lza_workbench.core.templates import resolve_template_source, validate_template
from lza_workbench.core.workspace import (
    create_workspace,
    normalize_customer_slug,
    validate_project_target,
)


def test_normalize_customer_slug() -> None:
    assert normalize_customer_slug("Comm-IT") == "comm-it"
    assert normalize_customer_slug(" ACME Customer ") == "acme-customer"
    assert normalize_customer_slug("ACME_Customer") == "acme-customer"
    assert normalize_customer_slug("ACME---Customer!!!") == "acme-customer"


def test_normalize_customer_slug_empty_result() -> None:
    with pytest.raises(ValueError, match="valid workspace slug"):
        normalize_customer_slug("!!!")


def test_collect_init_request_non_interactive_uses_defaults(tmp_path: Path) -> None:
    request = collect_init_request(
        customer_name="Comm-IT",
        workspace_dir=tmp_path,
        aws_profile=None,
        aws_region=None,
        lza_version=None,
        template_source=None,
        dry_run=False,
        force=False,
        skip_aws_check=True,
        interactive=False,
    )

    assert request.aws_profile == "comm-it"
    assert request.aws_region == "eu-west-1"
    assert request.lza_version == "v1.15.5"
    assert request.project_dir == tmp_path
    assert request.template_source == "default"
    assert request.template_source_type == "bundled"


def test_validate_project_target_rejects_existing_project_without_force(tmp_path: Path) -> None:
    project_dir = tmp_path / "comm-it"
    project_dir.mkdir()
    (project_dir / "lza-project.yaml").write_text("customer: {}\n", encoding="utf-8")

    with pytest.raises(typer.BadParameter, match="already exists"):
        validate_project_target(project_dir, force=False)


def test_validate_project_target_rejects_non_empty_directory_without_force(tmp_path: Path) -> None:
    project_dir = tmp_path / "comm-it"
    project_dir.mkdir()
    (project_dir / "notes.txt").write_text("keep me\n", encoding="utf-8")

    with pytest.raises(typer.BadParameter, match="not empty"):
        validate_project_target(project_dir, force=False)


def test_validate_project_target_allows_force_with_unrelated_files(tmp_path: Path) -> None:
    project_dir = tmp_path / "comm-it"
    project_dir.mkdir()
    (project_dir / "notes.txt").write_text("keep me\n", encoding="utf-8")

    validate_project_target(project_dir, force=True)


def test_validate_template_source_reports_missing_file(tmp_path: Path) -> None:
    template_dir = tmp_path / "default" / "aws-accelerator-config"
    template_dir.mkdir(parents=True)

    with pytest.raises(typer.BadParameter, match="missing required files"):
        validate_template(template_dir)


def test_default_template_source_is_bundled_with_package() -> None:
    template_source = resolve_template_source("default")

    assert template_source.source == "default"
    assert template_source.source_type == "bundled"
    validate_template(template_source.config_dir)


def test_resolve_template_source_accepts_local_template_path(tmp_path: Path) -> None:
    template_source = _make_template_source(tmp_path)

    resolved = resolve_template_source(str(template_source))

    assert resolved.source_type == "local"
    assert resolved.config_dir == template_source / "aws-accelerator-config"


def test_resolve_template_source_rejects_remote_sources_for_now() -> None:
    with pytest.raises(typer.BadParameter, match="not supported yet"):
        resolve_template_source("git:https://example.com/customer/lza-template.git")


def test_create_workspace_generates_expected_files(tmp_path: Path) -> None:
    template_source = _make_template_source(tmp_path)
    request = _request(tmp_path, template_source)

    create_workspace(request)

    project_file = request.project_dir / "lza-project.yaml"
    state_file = request.project_dir / ".lza" / "state.json"
    parameters_json = request.project_dir / "installer" / "parameters.json"

    assert project_file.is_file()
    assert (request.project_dir / "aws-accelerator-config" / "iam-config.yaml").is_file()
    assert (request.project_dir / ".lza" / "logs").is_dir()
    assert json.loads(state_file.read_text(encoding="utf-8")) == {
        "customer": "comm-it",
        "lza_version": "v1.12.1",
        "aws_profile": "comm-it-root",
        "aws_region": "eu-west-1",
        "installer_stack_name": "AWSAccelerator-InstallerStack",
        "config_location": "s3",
        "last_pipeline_execution_id": None,
    }
    assert json.loads(parameters_json.read_text(encoding="utf-8")) == {
        "control_tower_enabled": True,
        "enable_approval_stage": True,
        "enable_diagnostics_pack": True,
        "anonymous_data": False,
    }
    assert "template_source_type: local" in project_file.read_text(encoding="utf-8")


def test_run_init_dry_run_does_not_create_workspace(tmp_path: Path) -> None:
    template_source = _make_template_source(tmp_path)
    request = _request(tmp_path, template_source, dry_run=True, skip_aws_check=True)

    run_init(request)

    assert not request.project_dir.exists()


def test_run_init_force_replaces_generated_config_but_keeps_unrelated_files(tmp_path: Path) -> None:
    template_source = _make_template_source(tmp_path)
    request = _request(tmp_path, template_source)
    create_workspace(request)
    unrelated = request.project_dir / "notes.txt"
    unrelated.write_text("keep me\n", encoding="utf-8")
    stale_config = request.project_dir / "aws-accelerator-config" / "stale.yaml"
    stale_config.write_text("stale: true\n", encoding="utf-8")

    run_init(request.model_copy(update={"force": True, "skip_aws_check": True}))

    assert unrelated.read_text(encoding="utf-8") == "keep me\n"
    assert not stale_config.exists()


def test_run_init_validates_aws_profile_before_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template_source = _make_template_source(tmp_path)
    request = _request(tmp_path, template_source, skip_aws_check=False)

    def fail_validation(profile: str, region: str) -> dict[str, str]:
        raise typer.BadParameter(f"AWS profile validation failed for {profile} in {region}")

    monkeypatch.setattr("lza_workbench.commands.init.validate_aws_profile", fail_validation)

    with pytest.raises(typer.BadParameter, match="AWS profile validation failed"):
        run_init(request)
    assert not request.project_dir.exists()


def test_run_init_prints_successful_aws_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    template_source = _make_template_source(tmp_path)
    request = _request(tmp_path, template_source, skip_aws_check=False)

    def successful_validation(profile: str, region: str) -> dict[str, str]:
        assert profile == "comm-it-root"
        assert region == "eu-west-1"
        return {
            "account": "123456789012",
            "arn": "arn:aws:iam::123456789012:user/test",
            "user_id": "AID",
        }

    monkeypatch.setattr("lza_workbench.commands.init.validate_aws_profile", successful_validation)

    run_init(request)

    captured = capsys.readouterr()
    assert "123456789012" in captured.out
    assert "arn:aws:iam::123456789012:user/test" in captured.out


def test_cli_init_full_non_interactive_dry_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from lza_workbench.cli import main

    template_source = _make_template_source(tmp_path)
    workspace_dir = tmp_path / "comm-it"

    result = main(
        [
            "init",
            "Comm-IT",
            "--workspace-dir",
            str(workspace_dir),
            "--aws-profile",
            "comm-it-root",
            "--aws-region",
            "eu-west-1",
            "--lza-version",
            "v1.12.1",
            "--template-source",
            str(template_source),
            "--dry-run",
            "--skip-aws-check",
        ]
    )

    assert result == 0
    assert not workspace_dir.exists()
    assert "Dry run" in capsys.readouterr().out


def _request(
    tmp_path: Path,
    template_source: Path,
    *,
    dry_run: bool = False,
    skip_aws_check: bool = True,
) -> InitRequest:
    return InitRequest(
        customer_name="Comm-IT",
        customer_slug="comm-it",
        workspace_dir=tmp_path,
        project_dir=tmp_path / "comm-it",
        aws_profile="comm-it-root",
        aws_region="eu-west-1",
        lza_version="v1.12.1",
        template_source=str(template_source),
        template_source_type="local",
        template_config_dir=template_source / "aws-accelerator-config",
        dry_run=dry_run,
        force=False,
        skip_aws_check=skip_aws_check,
    )


def _make_template_source(tmp_path: Path) -> Path:
    template_source = tmp_path / "template"
    template_dir = template_source / "aws-accelerator-config"
    template_dir.mkdir(parents=True)
    for name in (
        "global-config.yaml",
        "organization-config.yaml",
        "accounts-config.yaml",
        "network-config.yaml",
        "security-config.yaml",
        "replacements-config.yaml",
        "iam-config.yaml",
    ):
        template_dir.joinpath(name).write_text("{}\n", encoding="utf-8")
    return template_source
