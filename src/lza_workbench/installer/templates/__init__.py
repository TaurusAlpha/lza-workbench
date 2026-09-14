"""CloudFormation template handling and inspection for the LZA installer."""

from lza_workbench.installer.templates.digest import (
    get_installer_template_digest,
    include_template_digest_change,
)
from lza_workbench.installer.templates.retrieval import (
    INSTALLER_TEMPLATE_FILENAME,
    INSTALLER_TEMPLATE_URL_TEMPLATE,
    LOCAL_PACKAGED_INSTALLER_TEMPLATE,
    configure_anonymous_data,
    download_installer_template,
    download_installer_template_content,
    extract_template_version,
    inspect_template_parameters,
    prepare_installer_template,
    resolve_installer_template,
    validate_parameters_against_schema,
)

__all__ = [
    "INSTALLER_TEMPLATE_FILENAME",
    "INSTALLER_TEMPLATE_URL_TEMPLATE",
    "LOCAL_PACKAGED_INSTALLER_TEMPLATE",
    "configure_anonymous_data",
    "download_installer_template",
    "download_installer_template_content",
    "extract_template_version",
    "get_installer_template_digest",
    "include_template_digest_change",
    "inspect_template_parameters",
    "prepare_installer_template",
    "resolve_installer_template",
    "validate_parameters_against_schema",
]
