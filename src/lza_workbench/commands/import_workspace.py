"""Implementation for adopting an existing LZA customer workspace."""

from __future__ import annotations

import copy
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from ruamel.yaml import YAML

from lza_workbench.commands import DEFAULT_AWS_REGION, DEFAULT_LZA_VERSION
from lza_workbench.core.project import (
    ImportRequest,
    InstallerSettings,
    project_metadata,
    state_metadata,
)
from lza_workbench.core.templates import REQUIRED_TEMPLATE_FILES, validate_template
from lza_workbench.core.workspace import normalize_customer_slug

console = Console()
CONFIG_DIRECTORY_NAME = "aws-accelerator-config"
PROJECT_FILE_NAME = "lza-project.yaml"
STATE_FILE = Path(".lza") / "state.json"


@dataclass
class ExistingMetadata:
    """Validated Workbench metadata loaded from an imported workspace."""

    project: Any
    state: dict[str, Any]


def collect_import_request(
    *,
    workspace: Path | None,
    customer_name: str | None,
    aws_profile: str | None,
    aws_region: str | None,
    lza_version: str | None,
    dry_run: bool,
    interactive: bool,
) -> ImportRequest:
    """Resolve import paths and collect new or updated metadata values."""
    project_dir, config_dir = resolve_import_workspace(workspace or Path.cwd())
    validate_import_config(config_dir)
    existing = load_existing_metadata(project_dir)

    existing_customer = _existing_value(existing, "customer", "name")
    selected_customer = _value_or_prompt(
        "Customer name",
        customer_name,
        default=existing_customer or project_dir.name,
        interactive=interactive,
    )
    existing_slug = _existing_value(existing, "customer", "slug")
    if existing_customer == selected_customer and existing_slug is not None:
        customer_slug = existing_slug
    else:
        customer_slug = normalize_customer_slug(selected_customer)

    selected_profile = _value_or_prompt(
        "AWS profile",
        aws_profile,
        default=_existing_value(existing, "aws", "profile") or customer_slug,
        interactive=interactive,
    )
    selected_region = _value_or_prompt(
        "AWS region",
        aws_region,
        default=_existing_value(existing, "aws", "region") or DEFAULT_AWS_REGION,
        interactive=interactive,
    )
    selected_version = _value_or_prompt(
        "LZA version",
        lza_version,
        default=_existing_value(existing, "lza", "version") or DEFAULT_LZA_VERSION,
        interactive=interactive,
    )

    return ImportRequest(
        customer_name=selected_customer,
        customer_slug=customer_slug,
        workspace_dir=project_dir,
        project_dir=project_dir,
        aws_profile=selected_profile,
        aws_region=selected_region,
        lza_version=selected_version,
        template_source=str(project_dir),
        template_config_dir=config_dir,
        dry_run=dry_run,
        installer=InstallerSettings(),
    )


def run_import(request: ImportRequest) -> None:
    """Create or update Workbench metadata without modifying customer config."""
    validate_import_config(request.template_config_dir)
    existing = load_existing_metadata(request.project_dir)
    if existing is None:
        desired_project = project_metadata(request)
        desired_state = state_metadata(request)
        changes = _initial_changes(request)
    else:
        desired_project = copy.deepcopy(existing.project)
        desired_state = copy.deepcopy(existing.state)
        _merge_request(desired_project, desired_state, request)
        changes = _metadata_changes(existing.project, desired_project)

    changed_paths = _changed_paths(
        request.project_dir,
        existing,
        desired_project,
        desired_state,
    )
    if request.dry_run:
        _print_summary("Dry run: lza import", request, changes, changed_paths)
        return
    if not changed_paths:
        console.print("[bold green]Workspace already imported; no metadata changes[/bold green]")
        console.print(f"Workspace: {request.project_dir}")
        return

    _write_import_metadata(
        request.project_dir,
        desired_project,
        desired_state,
        write_project=request.project_dir / PROJECT_FILE_NAME in changed_paths,
        write_state=request.project_dir / STATE_FILE in changed_paths,
    )
    _print_summary("Imported LZA project workspace", request, changes, changed_paths)


def resolve_import_workspace(path: Path) -> tuple[Path, Path]:
    """Resolve either a workspace root or its config directory."""
    supplied = path.expanduser().absolute()
    if supplied.name == CONFIG_DIRECTORY_NAME:
        config_dir = supplied
        project_dir = supplied.parent
    else:
        project_dir = supplied
        config_dir = supplied / CONFIG_DIRECTORY_NAME

    if not project_dir.exists():
        raise typer.BadParameter(f"Workspace directory does not exist: {project_dir}")
    if not project_dir.is_dir():
        raise typer.BadParameter(f"Workspace path is not a directory: {project_dir}")
    if config_dir.is_symlink():
        raise typer.BadParameter(f"Configuration directory must not be a symlink: {config_dir}")

    return project_dir.resolve(), config_dir.resolve()


def validate_import_config(config_dir: Path) -> None:
    """Apply structural validation plus import-specific symlink checks."""
    linked = [name for name in REQUIRED_TEMPLATE_FILES if (config_dir / name).is_symlink()]
    if linked:
        raise typer.BadParameter(
            f"Required configuration files must not be symlinks: {', '.join(linked)}"
        )
    validate_template(config_dir)


def load_existing_metadata(project_dir: Path) -> ExistingMetadata | None:
    """Load and validate an existing complete pair of Workbench metadata files."""
    project_path = project_dir / PROJECT_FILE_NAME
    state_path = project_dir / STATE_FILE
    if state_path.parent.is_symlink():
        raise typer.BadParameter(
            f"Metadata directory must not be a symlink: {state_path.parent}"
        )
    if project_path.is_symlink() or state_path.is_symlink():
        raise typer.BadParameter("Workbench metadata files must not be symlinks.")
    project_exists = project_path.exists()
    state_exists = state_path.exists()

    if project_exists != state_exists:
        raise typer.BadParameter(
            "Workspace has partial Workbench metadata; both "
            f"{PROJECT_FILE_NAME} and {STATE_FILE} are required."
        )
    if not project_exists:
        lza_dir = state_path.parent
        if lza_dir.is_symlink():
            raise typer.BadParameter(f"Metadata directory must not be a symlink: {lza_dir}")
        return None
    yaml = YAML()
    yaml.preserve_quotes = True
    try:
        project = yaml.load(project_path)
    except Exception as exc:
        raise typer.BadParameter(f"Invalid {PROJECT_FILE_NAME}: {exc}") from exc
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(f"Invalid {STATE_FILE}: {exc}") from exc

    _validate_project_metadata(project)
    _validate_state_metadata(state)
    _validate_metadata_consistency(project, state)
    return ExistingMetadata(project=project, state=state)


def _validate_project_metadata(project: Any) -> None:
    if not isinstance(project, dict):
        raise typer.BadParameter(f"{PROJECT_FILE_NAME} must contain a YAML mapping.")
    required_strings = (
        ("customer", "name"),
        ("customer", "slug"),
        ("aws", "profile"),
        ("aws", "region"),
        ("lza", "version"),
        ("lza", "accelerator_prefix"),
        ("lza", "config_repository_location"),
        ("lza", "template_source_type"),
        ("lza", "template_source"),
    )
    for path in required_strings:
        _require_nested_type(project, path, str, PROJECT_FILE_NAME)
    for name in (
        "control_tower_enabled",
        "enable_approval_stage",
        "enable_diagnostics_pack",
        "anonymous_data",
    ):
        _require_nested_type(project, ("installer", name), bool, PROJECT_FILE_NAME)


def _validate_state_metadata(state: Any) -> None:
    if not isinstance(state, dict):
        raise typer.BadParameter(f"{STATE_FILE} must contain a JSON object.")
    for name in (
        "customer",
        "lza_version",
        "aws_profile",
        "aws_region",
        "installer_stack_name",
        "config_location",
    ):
        _require_nested_type(state, (name,), str, str(STATE_FILE))
    if "last_pipeline_execution_id" not in state:
        raise typer.BadParameter(
            f"{STATE_FILE} is missing required field: last_pipeline_execution_id"
        )


def _require_nested_type(
    data: dict[str, Any],
    path: tuple[str, ...],
    expected_type: type,
    source: str,
) -> None:
    value: Any = data
    for key in path:
        if not isinstance(value, dict) or key not in value:
            raise typer.BadParameter(f"{source} is missing required field: {'.'.join(path)}")
        value = value[key]
    if not isinstance(value, expected_type):
        raise typer.BadParameter(
            f"{source} field {'.'.join(path)} must be {expected_type.__name__}."
        )


def _validate_metadata_consistency(project: Any, state: dict[str, Any]) -> None:
    mirrors = (
        (("customer", "slug"), "customer"),
        (("aws", "profile"), "aws_profile"),
        (("aws", "region"), "aws_region"),
        (("lza", "version"), "lza_version"),
        (("lza", "config_repository_location"), "config_location"),
    )
    inconsistent = [
        ".".join(project_path)
        for project_path, state_key in mirrors
        if _nested_value(project, *project_path) != state[state_key]
    ]
    if inconsistent:
        raise typer.BadParameter(
            "Workbench metadata fields disagree between project and state: "
            + ", ".join(inconsistent)
        )


def _merge_request(project: Any, state: dict[str, Any], request: ImportRequest) -> None:
    project["customer"]["name"] = request.customer_name
    project["customer"]["slug"] = request.customer_slug
    project["aws"]["profile"] = request.aws_profile
    project["aws"]["region"] = request.aws_region
    project["lza"]["version"] = request.lza_version
    state["customer"] = request.customer_slug
    state["aws_profile"] = request.aws_profile
    state["aws_region"] = request.aws_region
    state["lza_version"] = request.lza_version


def _metadata_changes(old: Any, new: Any) -> list[tuple[str, Any, Any]]:
    paths = (
        ("customer", "name"),
        ("customer", "slug"),
        ("aws", "profile"),
        ("aws", "region"),
        ("lza", "version"),
    )
    return [
        (".".join(path), _nested_value(old, *path), _nested_value(new, *path))
        for path in paths
        if _nested_value(old, *path) != _nested_value(new, *path)
    ]


def _initial_changes(request: ImportRequest) -> list[tuple[str, Any, Any]]:
    return [
        ("customer.name", None, request.customer_name),
        ("customer.slug", None, request.customer_slug),
        ("aws.profile", None, request.aws_profile),
        ("aws.region", None, request.aws_region),
        ("lza.version", None, request.lza_version),
        ("lza.template_source_type", None, request.template_source_type),
        ("lza.template_source", None, request.template_source),
    ]


def _changed_paths(
    project_dir: Path,
    existing: ExistingMetadata | None,
    desired_project: Any,
    desired_state: dict[str, Any],
) -> list[Path]:
    if existing is None:
        return [project_dir / PROJECT_FILE_NAME, project_dir / STATE_FILE]
    paths: list[Path] = []
    if existing.project != desired_project:
        paths.append(project_dir / PROJECT_FILE_NAME)
    if existing.state != desired_state:
        paths.append(project_dir / STATE_FILE)
    return paths


def _write_import_metadata(
    project_dir: Path,
    project: Any,
    state: dict[str, Any],
    *,
    write_project: bool,
    write_state: bool,
) -> None:
    state_dir = project_dir / STATE_FILE.parent
    if state_dir.is_symlink():
        raise typer.BadParameter(f"Metadata directory must not be a symlink: {state_dir}")
    state_dir.mkdir(parents=True, exist_ok=True)
    if write_project:
        _atomic_write_yaml(project_dir / PROJECT_FILE_NAME, project)
    if write_state:
        _atomic_write_json(project_dir / STATE_FILE, state)


def _atomic_write_yaml(path: Path, data: Any) -> None:
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.preserve_quotes = True
    _atomic_write(path, lambda handle: yaml.dump(data, handle))


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    _atomic_write(
        path,
        lambda handle: json.dump(data, handle, indent=2, sort_keys=False),
        suffix="\n",
    )


def _atomic_write(
    path: Path,
    writer: Any,
    *,
    suffix: str = "",
) -> None:
    mode = path.stat().st_mode if path.exists() else None
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            writer(handle)
            if suffix:
                handle.write(suffix)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temporary_path, mode)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _print_summary(
    title: str,
    request: ImportRequest,
    changes: list[tuple[str, Any, Any]],
    paths: list[Path],
) -> None:
    console.print(f"[bold green]{title}[/bold green]")
    console.print(f"Workspace: {request.project_dir}")
    console.print(f"Configuration: {request.template_config_dir}")
    if changes:
        console.print("Metadata changes:")
        for field, old, new in changes:
            console.print(f"  {field}: {_display_value(old)} -> {_display_value(new)}")
    else:
        console.print("Metadata changes: none")
    if paths:
        console.print("Affected paths:")
        for path in paths:
            console.print(f"  - {path}")
    else:
        console.print("Affected paths: none")
    console.print("Customer configuration files were preserved.")


def _display_value(value: Any) -> str:
    return "<missing>" if value is None else str(value)


def _existing_value(existing: ExistingMetadata | None, *path: str) -> str | None:
    if existing is None:
        return None
    value = _nested_value(existing.project, *path)
    return value if isinstance(value, str) else None


def _nested_value(data: Any, *path: str) -> Any:
    value = data
    for key in path:
        value = value[key]
    return value


def _value_or_prompt(
    label: str,
    value: str | None,
    *,
    default: str,
    interactive: bool,
) -> str:
    if value is not None:
        return value
    if interactive:
        return typer.prompt(label, default=default)
    return default
