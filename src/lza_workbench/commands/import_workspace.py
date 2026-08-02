"""Adopt an existing LZA customer workspace.

Validate its layout, collect metadata, and preserve customer-owned configuration.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError
from rich.console import Console
from ruamel.yaml import YAML

from lza_workbench.commands import DEFAULT_AWS_REGION, DEFAULT_LZA_VERSION
from lza_workbench.commands.init import resolve_init_workspace_dir
from lza_workbench.core.templates import REQUIRED_TEMPLATE_FILES, validate_template
from lza_workbench.core.workspace import (
    WORKSPACE_CONFIG_FILE,
    WORKSPACE_STATE_FILE,
    InstallerSettings,
    WorkspaceConfig,
    WorkspaceState,
    normalize_customer_slug,
)

console = Console()
CONFIG_DIRECTORY_NAME = "aws-accelerator-config"


@dataclass
class ExistingMetadata:
    """Validated metadata loaded from an imported workspace."""

    config: Any
    state: dict[str, Any]


@dataclass(frozen=True)
class ImportOptions:
    """Resolved values controlling one import command invocation."""

    customer_name: str
    customer_slug: str
    workspace_dir: Path
    aws_profile: str
    aws_region: str
    lza_version: str
    template_source: str
    template_source_type: str
    template_config_dir: Path
    dry_run: bool = False


def collect_import_options(
    *,
    workspace_dir: Path | None,
    customer_name: str,
    aws_profile: str | None,
    aws_region: str | None,
    lza_version: str | None,
    dry_run: bool,
    interactive: bool,
) -> ImportOptions:
    """Resolve import paths and collect new or updated metadata values."""
    requested_workspace_dir = resolve_init_workspace_dir(
        customer_name=customer_name,
        workspace_dir=workspace_dir,
        interactive=interactive,
    )
    workspace_dir, config_dir = resolve_import_workspace(requested_workspace_dir)
    validate_import_config(config_dir)
    existing = load_existing_metadata(workspace_dir)

    existing_customer = _existing_value(existing, "customer", "name")
    selected_customer = customer_name
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

    return ImportOptions(
        customer_name=selected_customer,
        customer_slug=customer_slug,
        workspace_dir=workspace_dir,
        aws_profile=selected_profile,
        aws_region=selected_region,
        lza_version=selected_version,
        template_source=str(workspace_dir),
        template_source_type="local",
        template_config_dir=config_dir,
        dry_run=dry_run,
    )


def run_import(request: ImportOptions) -> None:
    """Create or update workspace metadata without modifying customer config."""
    validate_import_config(request.template_config_dir)
    existing = load_existing_metadata(request.workspace_dir)
    if existing is None:
        config = build_workspace_config(request)
        desired_config = config.model_dump(mode="json")
        desired_state = WorkspaceState.from_config(config).model_dump(mode="json")
        changes = _initial_changes(request)
    else:
        desired_config = copy.deepcopy(existing.config)
        desired_state = copy.deepcopy(existing.state)
        _merge_request(desired_config, desired_state, request)
        changes = _metadata_changes(existing.config, desired_config)

    changed_paths = _changed_paths(
        request.workspace_dir,
        existing,
        desired_config,
        desired_state,
    )
    if request.dry_run:
        _print_summary("Dry run: lza import", request, changes, changed_paths)
        return
    if not changed_paths:
        console.print("[bold green]Workspace already imported; no metadata changes[/bold green]")
        console.print(f"Workspace: {request.workspace_dir}")
        return

    _write_import_metadata(
        request.workspace_dir,
        desired_config,
        desired_state,
        write_config=(
            request.workspace_dir / WORKSPACE_CONFIG_FILE in changed_paths
        ),
        write_state=request.workspace_dir / WORKSPACE_STATE_FILE in changed_paths,
    )
    _print_summary("Imported LZA workspace", request, changes, changed_paths)


def resolve_import_workspace(path: Path) -> tuple[Path, Path]:
    """Resolve either a workspace root or its config directory."""
    supplied = path.expanduser().absolute()
    if supplied.name == CONFIG_DIRECTORY_NAME:
        config_dir = supplied
        workspace_dir = supplied.parent
    else:
        workspace_dir = supplied
        config_dir = supplied / CONFIG_DIRECTORY_NAME

    if not workspace_dir.exists():
        raise typer.BadParameter(f"Workspace directory does not exist: {workspace_dir}")
    if not workspace_dir.is_dir():
        raise typer.BadParameter(f"Workspace path is not a directory: {workspace_dir}")
    if config_dir.is_symlink():
        raise typer.BadParameter(f"Configuration directory must not be a symlink: {config_dir}")

    return workspace_dir.resolve(), config_dir.resolve()


def validate_import_config(config_dir: Path) -> None:
    """Apply structural validation plus import-specific symlink checks."""
    linked = [name for name in REQUIRED_TEMPLATE_FILES if (config_dir / name).is_symlink()]
    if linked:
        raise typer.BadParameter(
            f"Required configuration files must not be symlinks: {', '.join(linked)}"
        )
    validate_template(config_dir)


def load_existing_metadata(workspace_dir: Path) -> ExistingMetadata | None:
    """Load and validate an existing complete pair of workspace metadata files."""
    config_path = workspace_dir / WORKSPACE_CONFIG_FILE
    state_path = workspace_dir / WORKSPACE_STATE_FILE
    if state_path.parent.is_symlink():
        raise typer.BadParameter(
            f"Metadata directory must not be a symlink: {state_path.parent}"
        )
    if config_path.is_symlink() or state_path.is_symlink():
        raise typer.BadParameter("Workspace metadata files must not be symlinks.")
    config_exists = config_path.exists()
    state_exists = state_path.exists()

    if config_exists != state_exists:
        raise typer.BadParameter(
            "Workspace has partial metadata; both "
            f"{WORKSPACE_CONFIG_FILE} and {WORKSPACE_STATE_FILE} are required."
        )
    if not config_exists:
        lza_dir = state_path.parent
        if lza_dir.is_symlink():
            raise typer.BadParameter(f"Metadata directory must not be a symlink: {lza_dir}")
        return None
    yaml = YAML()
    yaml.preserve_quotes = True
    try:
        config = yaml.load(config_path)
    except Exception as exc:
        raise typer.BadParameter(f"Invalid {WORKSPACE_CONFIG_FILE}: {exc}") from exc
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(f"Invalid {WORKSPACE_STATE_FILE}: {exc}") from exc

    _validate_workspace_config(config)
    _validate_state_metadata(state)
    _validate_metadata_consistency(config, state)
    return ExistingMetadata(config=config, state=state)


def _validate_workspace_config(config: Any) -> None:
    try:
        WorkspaceConfig.model_validate(config)
    except ValidationError as exc:
        raise typer.BadParameter(f"Invalid {WORKSPACE_CONFIG_FILE}: {exc}") from exc


def _validate_state_metadata(state: Any) -> None:
    try:
        WorkspaceState.model_validate(state)
    except ValidationError as exc:
        raise typer.BadParameter(f"Invalid {WORKSPACE_STATE_FILE}: {exc}") from exc


def _validate_metadata_consistency(config: Any, state: dict[str, Any]) -> None:
    mirrors = (
        (("customer", "slug"), "customer"),
        (("aws", "profile"), "aws_profile"),
        (("aws", "region"), "aws_region"),
        (("lza", "version"), "lza_version"),
        (("lza", "config_repository_location"), "config_location"),
    )
    inconsistent = [
        ".".join(config_path)
        for config_path, state_key in mirrors
        if _nested_value(config, *config_path) != state[state_key]
    ]
    if inconsistent:
        raise typer.BadParameter(
            "Workspace configuration and state fields disagree: "
            + ", ".join(inconsistent)
        )


def _merge_request(config: Any, state: dict[str, Any], request: ImportOptions) -> None:
    config["customer"]["name"] = request.customer_name
    config["customer"]["slug"] = request.customer_slug
    config["aws"]["profile"] = request.aws_profile
    config["aws"]["region"] = request.aws_region
    config["lza"]["version"] = request.lza_version
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


def _initial_changes(request: ImportOptions) -> list[tuple[str, Any, Any]]:
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
    workspace_dir: Path,
    existing: ExistingMetadata | None,
    desired_config: Any,
    desired_state: dict[str, Any],
) -> list[Path]:
    if existing is None:
        return [workspace_dir / WORKSPACE_CONFIG_FILE, workspace_dir / WORKSPACE_STATE_FILE]
    paths: list[Path] = []
    if existing.config != desired_config:
        paths.append(workspace_dir / WORKSPACE_CONFIG_FILE)
    if existing.state != desired_state:
        paths.append(workspace_dir / WORKSPACE_STATE_FILE)
    return paths


def _write_import_metadata(
    workspace_dir: Path,
    config: Any,
    state: dict[str, Any],
    *,
    write_config: bool,
    write_state: bool,
) -> None:
    state_dir = workspace_dir / WORKSPACE_STATE_FILE.parent
    if state_dir.is_symlink():
        raise typer.BadParameter(f"Metadata directory must not be a symlink: {state_dir}")
    state_dir.mkdir(parents=True, exist_ok=True)
    if write_config:
        _atomic_write_yaml(workspace_dir / WORKSPACE_CONFIG_FILE, config)
    if write_state:
        _atomic_write_json(workspace_dir / WORKSPACE_STATE_FILE, state)


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
    request: ImportOptions,
    changes: list[tuple[str, Any, Any]],
    paths: list[Path],
) -> None:
    console.print(f"[bold green]{title}[/bold green]")
    console.print(f"Workspace: {request.workspace_dir}")
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
    value = _nested_value(existing.config, *path)
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


def build_workspace_config(options: ImportOptions) -> WorkspaceConfig:
    """Build the persisted configuration produced by import."""
    return WorkspaceConfig.create(
        customer_name=options.customer_name,
        customer_slug=options.customer_slug,
        aws_profile=options.aws_profile,
        aws_region=options.aws_region,
        lza_version=options.lza_version,
        template_source=options.template_source,
        template_source_type=options.template_source_type,
        installer=InstallerSettings(),
    )
