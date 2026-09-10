"""Configuration template discovery, resolution, and rendering."""

from lza_workbench.configuration.templates.discovery import (
    DEFAULT_TEMPLATE_SOURCE,
    OPTIONAL_TEMPLATE_FILES,
    REQUIRED_TEMPLATE_FILES,
    ResolvedTemplateSource,
    list_packaged_templates,
    render_and_copy_template,
    resolve_template_source,
    validate_template,
)
from lza_workbench.configuration.templates.rendering import (
    PLACEHOLDER_PATTERN,
    STANDARD_CONFIG_PATHS,
    capture_init_values_snapshot,
    compute_config_directory_digest,
    render_template_text,
    resolve_path_value,
)

__all__ = [
    "DEFAULT_TEMPLATE_SOURCE",
    "OPTIONAL_TEMPLATE_FILES",
    "PLACEHOLDER_PATTERN",
    "REQUIRED_TEMPLATE_FILES",
    "ResolvedTemplateSource",
    "STANDARD_CONFIG_PATHS",
    "capture_init_values_snapshot",
    "compute_config_directory_digest",
    "list_packaged_templates",
    "render_and_copy_template",
    "render_template_text",
    "resolve_path_value",
    "resolve_template_source",
    "validate_template",
]
