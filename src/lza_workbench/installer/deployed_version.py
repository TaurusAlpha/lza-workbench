"""Resolve the LZA version of a deployed installer stack."""

from __future__ import annotations

from typing import Any

from lza_workbench.aws.cloudformation import get_cloudformation_stack_template
from lza_workbench.aws.ssm import get_parameter_value
from lza_workbench.installer.templates import extract_template_version
from lza_workbench.installer.versions import normalize_lza_version


def installer_version_parameter_name(accelerator_prefix: str, stack_name: str) -> str:
    """Return the installer-version SSM parameter name used by the LZA template."""
    prefix = accelerator_prefix.strip() or "AWSAccelerator"
    one_word_prefix = "accelerator" if prefix.lower() == "awsaccelerator" else prefix
    return f"/{one_word_prefix}/{stack_name.strip()}/version"


def resolve_deployed_installer_version(
    *,
    cfn_client: Any | None,
    ssm_client: Any | None,
    stack_name: str,
    accelerator_prefix: str,
) -> str | None:
    """Resolve a live installer version from SSM, then its stack template description."""
    parameter_name = installer_version_parameter_name(accelerator_prefix, stack_name)
    parameter_value = get_parameter_value(name=parameter_name, client=ssm_client)
    if parameter_value is not None:
        return normalize_lza_version(parameter_value)

    template_body = get_cloudformation_stack_template(client=cfn_client, stack_name=stack_name)
    if template_body is None:
        return None
    return extract_template_version(template_body)
