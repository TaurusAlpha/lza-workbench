"""Resolve and render dynamic placeholders in LZA configuration templates."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lza_workbench.workspace.schema import WorkspaceConfig

PLACEHOLDER_PATTERN = re.compile(r"\$\{([a-zA-Z0-9_.]+)\}")


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
