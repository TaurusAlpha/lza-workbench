"""Resolve and render dynamic placeholders in LZA configuration templates."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lza_workbench.workspace.schema import WorkspaceConfig

PLACEHOLDER_PATTERN = re.compile(r"\$\{([a-zA-Z0-9_.]+)\}")

STANDARD_CONFIG_PATHS = (
    "customer.slug",
    "customer.name",
    "lza.accelerator_prefix",
    "aws.region",
    "installer.options.management_account_email",
    "installer.options.log_archive_account_email",
    "installer.options.audit_account_email",
)


def resolve_path_value(obj: Any, path: str) -> str | None:
    """Dynamically resolve a dot-separated attribute or key path from an object.

    Supports paths starting with or without 'config.' prefix (e.g.
    'customer.slug' or 'config.customer.slug').
    """
    if path.startswith("config."):
        path = path[len("config."):]

    current: Any = obj
    for part in path.split("."):
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return None

    if current is None:
        return None

    if isinstance(current, (str, int, float, bool)):
        val_str = str(current).strip()
        return val_str if val_str else None

    return None


def capture_init_values_snapshot(
    config: WorkspaceConfig,
    paths: tuple[str, ...] = STANDARD_CONFIG_PATHS,
) -> dict[str, str]:
    """Capture a snapshot dictionary of resolved configuration values."""
    snapshot: dict[str, str] = {}
    for p in paths:
        val = resolve_path_value(config, p)
        if val is not None:
            snapshot[p] = val
    return snapshot


def compute_config_directory_digest(config_dir: Path) -> str:
    """Compute a deterministic SHA-256 digest of all files in a configuration directory."""
    if not config_dir.is_dir():
        return ""

    hasher = hashlib.sha256()
    for file_path in sorted(config_dir.rglob("*")):
        if file_path.is_file():
            rel = file_path.relative_to(config_dir).as_posix()
            hasher.update(rel.encode("utf-8"))
            hasher.update(file_path.read_bytes())
    return hasher.hexdigest()


def render_template_text(content: str, config: WorkspaceConfig) -> tuple[str, list[str]]:
    """Render placeholders in template text using dynamic values from WorkspaceConfig.

    Replaces `${path.to.field}` when a non-empty resolved value exists in `config`.
    Preserves unresolved placeholders in the text and returns their names.
    LZA-native double-curly syntax (e.g. `{{ HomeRegion }}`) is untouched.

    Returns:
        A tuple of (rendered_content, list_of_unresolved_placeholder_tokens).
    """
    unresolved: list[str] = []

    def _replace_match(match: re.Match[str]) -> str:
        full_token = match.group(0)
        field_path = match.group(1)

        value = resolve_path_value(config, field_path)
        if value is not None:
            return value

        if full_token not in unresolved:
            unresolved.append(full_token)
        return full_token

    rendered = PLACEHOLDER_PATTERN.sub(_replace_match, content)
    return rendered, unresolved
