from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer

from lza_workbench.cli import main
from lza_workbench.commands.import_workspace import (collect_import_request,
                                                     run_import)
from lza_workbench.core.templates import REQUIRED_TEMPLATE_FILES


def test_import_new_workspace_preserves_config_and_creates_only_metadata(
    tmp_path: Path,
) -> None:
    workspace = _make_workspace(tmp_path)
    config_before = _config_snapshot(workspace)
    request = _collect(workspace)

    run_import(request)

    assert _config_snapshot(workspace) == config_before
    assert (workspace / "lza-project.yaml").is_file()
    assert (workspace / ".lza" / "state.json").is_file()
    assert sorted(path.name for path in (workspace / ".lza").iterdir()) == ["state.json"]
    assert not (workspace / "aws-accelerator-installer").exists()
    assert not (workspace / ".lza" / "logs").exists()

    project_text = (workspace / "lza-project.yaml").read_text(encoding="utf-8")
    assert "template_source_type: local" in project_text
    assert f"template_source: {workspace}" in project_text


def test_import_accepts_config_directory_path(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)

    request = _collect(workspace / "aws-accelerator-config")

    assert request.project_dir == workspace
    assert request.template_config_dir == workspace / "aws-accelerator-config"


def test_import_defaults_to_current_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _make_workspace(tmp_path)
    monkeypatch.chdir(workspace)

    request = _collect(None)

    assert request.project_dir == workspace
    assert request.customer_name == workspace.name


def test_import_dry_run_does_not_write_metadata(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = _make_workspace(tmp_path)
    request = _collect(workspace, dry_run=True)

    run_import(request)

    assert not (workspace / "lza-project.yaml").exists()
    assert not (workspace / ".lza").exists()
    output = capsys.readouterr().out
    assert "Dry run: lza import" in output
    assert "customer.name" in output
    assert "Affected paths" in output


def test_import_rejects_missing_required_files(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    (workspace / "aws-accelerator-config" / REQUIRED_TEMPLATE_FILES[0]).unlink()

    with pytest.raises(typer.BadParameter, match="missing required files"):
        _collect(workspace)


def test_import_rejects_unsupported_layout(tmp_path: Path) -> None:
    workspace = tmp_path / "customer"
    nested = workspace / "nested" / "aws-accelerator-config"
    nested.mkdir(parents=True)

    with pytest.raises(typer.BadParameter, match="Template directory does not exist"):
        _collect(workspace)


def test_import_rejects_symlinked_config_directory(tmp_path: Path) -> None:
    workspace = tmp_path / "customer"
    workspace.mkdir()
    external = _make_workspace(tmp_path, "external") / "aws-accelerator-config"
    (workspace / "aws-accelerator-config").symlink_to(external, target_is_directory=True)

    with pytest.raises(typer.BadParameter, match="must not be a symlink"):
        _collect(workspace)


def test_import_rejects_symlinked_required_file(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    required = workspace / "aws-accelerator-config" / REQUIRED_TEMPLATE_FILES[0]
    external = tmp_path / "external.yaml"
    external.write_text("{}\n", encoding="utf-8")
    required.unlink()
    required.symlink_to(external)

    with pytest.raises(typer.BadParameter, match="files must not be symlinks"):
        _collect(workspace)


def test_import_rejects_partial_metadata(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    (workspace / "lza-project.yaml").write_text("customer: {}\n", encoding="utf-8")

    with pytest.raises(typer.BadParameter, match="partial Workbench metadata"):
        _collect(workspace)


def test_import_rejects_malformed_metadata(tmp_path: Path) -> None:
    workspace = _make_imported_workspace(tmp_path)
    (workspace / "lza-project.yaml").write_text("not: [valid\n", encoding="utf-8")

    with pytest.raises(typer.BadParameter, match="Invalid lza-project.yaml"):
        _collect(workspace)


def test_import_rejects_inconsistent_metadata(tmp_path: Path) -> None:
    workspace = _make_imported_workspace(tmp_path)
    state_path = workspace / ".lza" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["aws_region"] = "us-east-1"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(typer.BadParameter, match="metadata fields disagree"):
        _collect(workspace)


def test_repeat_import_merges_explicit_values_and_preserves_unknown_data(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = _make_imported_workspace(tmp_path)
    project_path = workspace / "lza-project.yaml"
    project_text = project_path.read_text(encoding="utf-8")
    project_path.write_text(
        "# customer project\n" + project_text + "custom:\n  retained: true\n",
        encoding="utf-8",
    )
    state_path = workspace / ".lza" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["deployment"] = {"status": "SUCCEEDED"}
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    request = _collect(workspace, aws_region="us-east-1")
    run_import(request)

    updated_project = project_path.read_text(encoding="utf-8")
    updated_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert updated_project.startswith("# customer project\n")
    assert "custom:" in updated_project
    assert "region: us-east-1" in updated_project
    assert updated_state["aws_region"] == "us-east-1"
    assert updated_state["deployment"] == {"status": "SUCCEEDED"}
    output = capsys.readouterr().out
    assert "aws.region: eu-west-1 -> us-east-1" in output


def test_repeat_import_with_identical_values_is_noop(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = _make_imported_workspace(tmp_path)
    project_path = workspace / "lza-project.yaml"
    state_path = workspace / ".lza" / "state.json"
    before = (project_path.read_bytes(), state_path.read_bytes())

    run_import(_collect(workspace))

    assert (project_path.read_bytes(), state_path.read_bytes()) == before
    assert not list(workspace.glob(".*.tmp"))
    assert not list((workspace / ".lza").glob(".*.tmp"))
    assert "already imported; no metadata changes" in capsys.readouterr().out


def test_cli_import_non_interactive(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)

    result = main(
        [
            "import",
            str(workspace),
            "--customer-name",
            "Comm-IT",
            "--aws-profile",
            "comm-it-root",
            "--aws-region",
            "eu-west-1",
            "--lza-version",
            "v1.12.1",
        ]
    )

    assert result == 0
    assert (workspace / "lza-project.yaml").is_file()


def test_interactive_init_accepts_import_and_ignores_template(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = _make_workspace(tmp_path)
    monkeypatch.setattr("lza_workbench.cli._is_interactive", lambda: True)
    monkeypatch.setattr("lza_workbench.cli.typer.confirm", lambda _: True)

    result = main(
        [
            "init",
            "Comm-IT",
            "--workspace-dir",
            str(workspace),
            "--aws-profile",
            "comm-it-root",
            "--aws-region",
            "eu-west-1",
            "--lza-version",
            "v1.12.1",
            "--template-source",
            "/unused/template",
        ]
    )

    assert result == 0
    assert (workspace / "lza-project.yaml").is_file()
    assert "template source is ignored" in capsys.readouterr().out


def test_interactive_init_declines_import_cleanly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = _make_workspace(tmp_path)
    monkeypatch.setattr("lza_workbench.cli._is_interactive", lambda: True)
    monkeypatch.setattr("lza_workbench.cli.typer.confirm", lambda _: False)

    result = main(["init", "Comm-IT", "--workspace-dir", str(workspace)])

    assert result == 0
    assert not (workspace / "lza-project.yaml").exists()
    assert "no changes were made" in capsys.readouterr().out


def test_noninteractive_init_recommends_import(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)

    result = main(["init", "Comm-IT", "--workspace-dir", str(workspace)])

    assert result != 0


def test_interactive_repeat_import_prompts_with_existing_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _make_imported_workspace(tmp_path)
    answers = iter(("Renamed Customer", "comm-it-root", "eu-central-1", "v1.15.5"))
    defaults: list[str] = []

    def prompt(label: str, default: str) -> str:
        defaults.append(f"{label}={default}")
        return next(answers)

    monkeypatch.setattr("lza_workbench.commands.import_workspace.typer.prompt", prompt)
    request = collect_import_request(
        workspace=workspace,
        customer_name=None,
        aws_profile=None,
        aws_region=None,
        lza_version=None,
        dry_run=False,
        interactive=True,
    )
    run_import(request)

    project_text = (workspace / "lza-project.yaml").read_text(encoding="utf-8")
    assert defaults[0] == "Customer name=comm-it"
    assert "name: Renamed Customer" in project_text
    assert "slug: renamed-customer" in project_text
    assert "region: eu-central-1" in project_text


def test_init_force_bypasses_import_offer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _make_workspace(tmp_path)
    stale_file = workspace / "aws-accelerator-config" / "stale.yaml"
    stale_file.write_text("stale: true\n", encoding="utf-8")
    monkeypatch.setattr("lza_workbench.cli._is_interactive", lambda: True)

    def unexpected_confirm(_: str) -> bool:
        raise AssertionError("init --force must not offer import")

    monkeypatch.setattr("lza_workbench.cli.typer.confirm", unexpected_confirm)
    result = main(
        [
            "init",
            "Comm-IT",
            "--workspace-dir",
            str(workspace),
            "--aws-profile",
            "comm-it-root",
            "--aws-region",
            "eu-west-1",
            "--lza-version",
            "v1.15.5",
            "--template-source",
            "default",
            "--skip-aws-check",
            "--force",
        ]
    )

    assert result == 0
    assert not stale_file.exists()


def _collect(
    workspace: Path | None,
    *,
    aws_region: str | None = None,
    dry_run: bool = False,
):
    return collect_import_request(
        workspace=workspace,
        customer_name=None,
        aws_profile=None,
        aws_region=aws_region,
        lza_version=None,
        dry_run=dry_run,
        interactive=False,
    )


def _make_workspace(tmp_path: Path, name: str = "comm-it") -> Path:
    workspace = tmp_path / name
    config_dir = workspace / "aws-accelerator-config"
    config_dir.mkdir(parents=True)
    for index, filename in enumerate(REQUIRED_TEMPLATE_FILES):
        config_dir.joinpath(filename).write_text(
            f"# preserved {index}\nvalue: {index}\n",
            encoding="utf-8",
        )
    config_dir.joinpath("iam-config.yaml").write_text("custom: true\n", encoding="utf-8")
    return workspace.resolve()


def _make_imported_workspace(tmp_path: Path) -> Path:
    workspace = _make_workspace(tmp_path)
    run_import(_collect(workspace))
    return workspace


def _config_snapshot(workspace: Path) -> dict[str, bytes]:
    config_dir = workspace / "aws-accelerator-config"
    return {path.name: path.read_bytes() for path in config_dir.iterdir()}
