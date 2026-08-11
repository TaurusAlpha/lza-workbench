"""Resolve and validate LZA configuration templates."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from lza_workbench.core.errors import LzaError
from lza_workbench.utils.output import console, print_warning

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


def resolve_template_source(template_source: str) -> ResolvedTemplateSource:
    """Resolve a user-facing template source string to an aws-accelerator-config path."""
    if template_source == DEFAULT_TEMPLATE_SOURCE:
        return ResolvedTemplateSource(
            source=DEFAULT_TEMPLATE_SOURCE,
            source_type="bundled",
            config_dir=_bundled_default_template_dir(),
        )

    if _looks_like_future_remote_source(template_source):
        raise LzaError("Remote template sources are not supported yet.")

    source_path = Path(template_source).expanduser().resolve()
    return ResolvedTemplateSource(
        source=str(source_path),
        source_type="local",
        config_dir=_local_template_config_dir(source_path),
    )


def validate_template(template_config_dir: Path) -> None:
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
        console.print(f"[bold red]Template is missing required files: {missing_list}[/bold red]")
    if missing_optional:
        missing_list = ", ".join(missing_optional)
        print_warning(f"Template is missing optional files: {missing_list}")


def _bundled_default_template_dir() -> Path:
    return Path(str(files("lza_workbench.templates"))) / "default" / "aws-accelerator-config"


def _local_template_config_dir(source_path: Path) -> Path:
    if source_path.name == "aws-accelerator-config":
        return source_path
    return source_path / "aws-accelerator-config"


def _looks_like_future_remote_source(template_source: str) -> bool:
    return template_source.startswith(("git:", "github:", "bitbucket:")) or "://" in template_source
