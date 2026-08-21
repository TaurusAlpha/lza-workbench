"""Resolve and validate LZA configuration templates."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING

from lza_workbench.configuration.rendering import render_template_text
from lza_workbench.errors import LzaError

if TYPE_CHECKING:
    from lza_workbench.workspace.schema import WorkspaceConfig

DEFAULT_TEMPLATE_SOURCE = "default"
REQUIRED_TEMPLATE_FILES = (
    "global-config.yaml",
    "organization-config.yaml",
    "accounts-config.yaml",
    "network-config.yaml",
    "security-config.yaml",
)

OPTIONAL_TEMPLATE_FILES = (
    "replacements-config.yaml",
    "customizations-config.yaml",
)


@dataclass(frozen=True)
class ResolvedTemplateSource:
    """Resolved template source details used by init."""

    source: str
    source_type: str
    config_dir: Path


def list_packaged_templates() -> list[str]:
    """List available packaged configuration template names."""
    templates_root = Path(str(files("lza_workbench.resources.configuration_templates")))
    if not templates_root.is_dir():
        return []

    templates: list[str] = []
    for item in sorted(templates_root.iterdir()):
        if item.is_dir() and not item.name.startswith((".", "_")):
            if (item / "aws-accelerator-config").is_dir():
                templates.append(item.name)
    return templates


def resolve_template_source(template_source: str) -> ResolvedTemplateSource:
    """Resolve a user-facing template source string to an aws-accelerator-config path."""
    if _looks_like_future_remote_source(template_source):
        raise LzaError("Remote template sources are not supported yet.")

    packaged = list_packaged_templates()
    if template_source in packaged:
        bundled_dir = _bundled_template_dir(template_source)
        return ResolvedTemplateSource(
            source=template_source,
            source_type="bundled",
            config_dir=bundled_dir,
        )

    source_path = Path(template_source).expanduser()
    if source_path.exists():
        resolved_path = source_path.resolve()
        return ResolvedTemplateSource(
            source=str(resolved_path),
            source_type="local",
            config_dir=_local_template_config_dir(resolved_path),
        )

    available = ", ".join(packaged) if packaged else "none"
    raise LzaError(
        f"Packaged configuration template '{template_source}' was not found. "
        f"Available packaged templates: {available}"
    )


def validate_template(
    template_config_dir: Path, *, on_warning: Callable[[str], None] | None = None
) -> None:
    """Validate that an aws-accelerator-config template has required files."""
    if not template_config_dir.is_dir():
        raise LzaError(f"Template directory does not exist: {template_config_dir}")

    missing_required = [
        name for name in REQUIRED_TEMPLATE_FILES if not (template_config_dir / name).is_file()
    ]
    missing_optional = [
        name for name in OPTIONAL_TEMPLATE_FILES if not (template_config_dir / name).is_file()
    ]

    if missing_required:
        missing_list = ", ".join(missing_required)
        raise LzaError(f"Template is missing required files: {missing_list}")
    if missing_optional and on_warning is not None:
        missing_list = ", ".join(missing_optional)
        on_warning(f"Template is missing optional files: {missing_list}")


def render_and_copy_template(
    template_config_dir: Path,
    target_config_dir: Path,
    config: WorkspaceConfig,
    dry_run: bool = False,
) -> tuple[list[Path], list[str]]:
    """Render template files with workspace values and copy to target directory.

    Returns:
        A tuple of (list_of_written_file_paths, list_of_unresolved_placeholders).
    """
    written_paths: list[Path] = []
    all_unresolved: list[str] = []

    if not dry_run:
        target_config_dir.mkdir(parents=True, exist_ok=True)

    text_extensions = {".yaml", ".yml", ".json", ".txt", ".md"}

    for item in sorted(template_config_dir.rglob("*")):
        if item.is_file():
            rel_path = item.relative_to(template_config_dir)
            dest_path = target_config_dir / rel_path
            written_paths.append(dest_path)

            if item.suffix.lower() in text_extensions:
                content = item.read_text(encoding="utf-8")
                rendered, unresolved = render_template_text(content, config)
                for unres in unresolved:
                    if unres not in all_unresolved:
                        all_unresolved.append(unres)
                if not dry_run:
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    dest_path.write_text(rendered, encoding="utf-8")
            else:
                if not dry_run:
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dest_path)

    return written_paths, all_unresolved


def _bundled_template_dir(template_name: str) -> Path:
    return (
        Path(str(files("lza_workbench.resources.configuration_templates")))
        / template_name
        / "aws-accelerator-config"
    )


def _local_template_config_dir(source_path: Path) -> Path:
    if source_path.name == "aws-accelerator-config":
        return source_path
    return source_path / "aws-accelerator-config"


def _looks_like_future_remote_source(template_source: str) -> bool:
    return template_source.startswith(("git:", "github:", "bitbucket:")) or "://" in template_source
