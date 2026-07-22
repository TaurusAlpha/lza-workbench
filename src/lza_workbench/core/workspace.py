"""Customer workspace path handling and file generation."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import typer

from lza_workbench.core.project import (
    InitRequest,
    installer_parameters,
    project_metadata,
    state_metadata,
    write_json,
    write_yaml,
)


def normalize_customer_slug(customer_name: str) -> str:
    """Normalize a customer name into a filesystem-safe slug."""
    slug = customer_name.strip().lower()
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"[^a-z0-9-]+", "", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    if not slug:
        raise ValueError("Customer name does not produce a valid workspace slug.")
    return slug


def validate_project_target(project_dir: Path, force: bool) -> None:
    """Prevent accidental overwrite of an existing project directory."""
    if not project_dir.exists():
        return
    if not project_dir.is_dir():
        raise typer.BadParameter(f"Target path exists and is not a directory: {project_dir}")
    if force:
        return
    if (project_dir / "lza-project.yaml").exists():
        raise typer.BadParameter(f"LZA project already exists: {project_dir}")
    if any(project_dir.iterdir()):
        raise typer.BadParameter(f"Target directory is not empty: {project_dir}")


def create_workspace(request: InitRequest) -> None:
    """Create or reinitialize generated workspace files."""
    request.project_dir.mkdir(parents=True, exist_ok=True)
    (request.project_dir / ".lza" / "logs").mkdir(parents=True, exist_ok=True)
    (request.project_dir / "installer").mkdir(parents=True, exist_ok=True)

    _replace_directory(
        source=request.template_config_dir,
        destination=request.project_dir / "aws-accelerator-config",
    )
    write_yaml(request.project_dir / "lza-project.yaml", project_metadata(request))
    write_yaml(request.project_dir / "installer" / "parameters.yaml", installer_parameters(request))
    write_json(request.project_dir / "installer" / "parameters.json", installer_parameters(request))
    write_json(request.project_dir / ".lza" / "state.json", state_metadata(request))


def planned_write_paths(request: InitRequest) -> list[Path]:
    return [
        request.project_dir,
        request.project_dir / "lza-project.yaml",
        request.project_dir / "aws-accelerator-config",
        request.project_dir / "installer" / "parameters.yaml",
        request.project_dir / "installer" / "parameters.json",
        request.project_dir / ".lza" / "state.json",
        request.project_dir / ".lza" / "logs",
    ]


def _replace_directory(*, source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
