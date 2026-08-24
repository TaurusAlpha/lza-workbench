"""Validation utilities for LZA configuration files and schemas."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError
from ruamel.yaml.nodes import MappingNode, ScalarNode, SequenceNode

from lza_workbench.errors import LzaError
from lza_workbench.installer.versions import normalize_lza_version

REQUIRED_LZA_CONFIG_FILES = (
    "global-config.yaml",
    "organization-config.yaml",
    "accounts-config.yaml",
    "network-config.yaml",
    "security-config.yaml",
    "iam-config.yaml",
)

OPTIONAL_LZA_CONFIG_FILES = (
    "replacements-config.yaml",
    "customizations-config.yaml",
)

ALL_LZA_CONFIG_FILES = REQUIRED_LZA_CONFIG_FILES + OPTIONAL_LZA_CONFIG_FILES
MANDATORY_ACCOUNT_NAMES = {"Management", "LogArchive", "Audit"}


def _custom_tag_constructor(loader: Any, tag_suffix: str, node: Any) -> Any:
    """Handle custom YAML tags (such as CloudFormation !Ref, !Sub) gracefully."""
    if isinstance(node, ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, MappingNode):
        return loader.construct_mapping(node)
    return str(node)


def _is_placeholder(val: Any) -> bool:
    """Check if a value is an un-rendered replacement variable or template placeholder."""
    if isinstance(val, str):
        cleaned = val.strip()
        return (
            (cleaned.startswith("{{") and cleaned.endswith("}}"))
            or (cleaned.startswith("${") and cleaned.endswith("}"))
        )
    return False


def _sanitize_template_placeholders(content: str) -> str:
    """Safely quote unquoted Mustache/Jinja-style template placeholders so YAML parser succeeds."""
    pattern = re.compile(r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|(\{\{[^{}\n]+\}\}))')

    def replacer(match: re.Match[str]) -> str:
        unquoted_mustache = match.group(2)
        if unquoted_mustache:
            return f'"{unquoted_mustache}"'
        return match.group(1)

    return pattern.sub(replacer, content)


def parse_yaml_file(file_path: Path) -> Any:
    """Parse a single YAML file and return its data, raising a clean LzaError on syntax error."""
    yaml = YAML(typ="safe")
    yaml.constructor.add_multi_constructor("!", _custom_tag_constructor)
    try:
        raw_content = file_path.read_text(encoding="utf-8")
        sanitized_content = _sanitize_template_placeholders(raw_content)
        return yaml.load(sanitized_content)
    except YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
        problem = getattr(exc, "problem", str(exc))
        raise LzaError(f"Invalid YAML syntax in '{file_path.name}'{location}: {problem}") from exc
    except OSError as exc:
        raise LzaError(f"Failed to read configuration file '{file_path}': {exc}") from exc


def validate_yaml_syntax(config_dir: Path) -> dict[str, Any]:
    """Parse and validate YAML syntax for core (required and optional) LZA configuration files.

    Returns:
        Dictionary mapping canonical file names to parsed data.
    """
    if not config_dir.is_dir():
        raise LzaError(f"Configuration directory does not exist: {config_dir}")

    parsed_files: dict[str, Any] = {}

    for filename in ALL_LZA_CONFIG_FILES:
        target_file = config_dir / filename
        if not target_file.is_file():
            # Check .yml extension alternative
            alt_name = filename.rsplit(".", 1)[0] + ".yml"
            alt_file = config_dir / alt_name
            if alt_file.is_file():
                target_file = alt_file

        if target_file.is_file():
            parsed = parse_yaml_file(target_file)
            parsed_files[filename] = parsed

    return parsed_files


def validate_lza_configuration_schema(
    config_dir: Path,
    lza_version: str | None = None,
    parsed_files: dict[str, Any] | None = None,
) -> None:
    """Validate official LZA top-level configuration schemas and structure."""
    if parsed_files is None:
        parsed_files = validate_yaml_syntax(config_dir)

    normalized_version = normalize_lza_version(lza_version) if lza_version else "latest"

    # 1. Validate required files exist and are mappings
    for required_file in REQUIRED_LZA_CONFIG_FILES:
        if required_file not in parsed_files:
            raise LzaError(f"Configuration is missing required file: '{required_file}'")
        data = parsed_files[required_file]
        if not isinstance(data, dict):
            raise LzaError(
                f"Configuration file '{required_file}' must contain a YAML mapping (dictionary)."
            )

    # 2. Validate global-config.yaml
    global_config = parsed_files["global-config.yaml"]
    _validate_global_config(global_config)

    # 3. Validate organization-config.yaml
    org_config = parsed_files["organization-config.yaml"]
    _validate_organization_config(org_config)

    # 4. Validate accounts-config.yaml
    accounts_config = parsed_files["accounts-config.yaml"]
    _validate_accounts_config(accounts_config)

    # 5. Validate network-config.yaml
    network_config = parsed_files["network-config.yaml"]
    _validate_network_config(network_config)

    # 6. Validate security-config.yaml
    security_config = parsed_files["security-config.yaml"]
    _validate_security_config(security_config)

    # 7. Validate iam-config.yaml
    iam_config = parsed_files["iam-config.yaml"]
    _validate_iam_config(iam_config)

    # Version-specific checks
    _validate_version_compatibility(normalized_version, parsed_files)


def _validate_global_config(data: dict[str, Any]) -> None:
    if "homeRegion" not in data or not str(data["homeRegion"]).strip():
        raise LzaError("global-config.yaml is missing required field: 'homeRegion'")
    if "enabledRegions" not in data:
        raise LzaError("global-config.yaml is missing required field: 'enabledRegions'")
    regions = data["enabledRegions"]
    if not (isinstance(regions, list) or _is_placeholder(regions)):
        raise LzaError(
            "global-config.yaml must define 'enabledRegions' as a list or replacement variable"
        )
    if isinstance(regions, list) and not regions:
        raise LzaError("global-config.yaml 'enabledRegions' must contain at least one region")


def _validate_organization_config(data: dict[str, Any]) -> None:
    if "organizationalUnits" in data:
        ous = data["organizationalUnits"]
        if not (isinstance(ous, list) or _is_placeholder(ous)):
            raise LzaError("organization-config.yaml 'organizationalUnits' must be a list")


def _validate_accounts_config(data: dict[str, Any]) -> None:
    if "mandatoryAccounts" not in data:
        raise LzaError("accounts-config.yaml is missing required field: 'mandatoryAccounts'")
    accounts = data["mandatoryAccounts"]
    if _is_placeholder(accounts):
        return
    if not isinstance(accounts, list):
        raise LzaError("accounts-config.yaml must define 'mandatoryAccounts' as a list")

    accounts = data["mandatoryAccounts"]
    account_names: set[str] = set()

    for idx, account in enumerate(accounts):
        if not isinstance(account, dict):
            raise LzaError(f"accounts-config.yaml mandatoryAccounts[{idx}] must be a mapping")
        name = account.get("name")
        if not name or not str(name).strip():
            raise LzaError(f"accounts-config.yaml mandatoryAccounts[{idx}] is missing 'name'")
        account_names.add(str(name).strip())
        if "email" not in account:
            raise LzaError(f"accounts-config.yaml account '{name}' is missing required 'email'")
        if "organizationalUnit" not in account:
            raise LzaError(
                f"accounts-config.yaml account '{name}' is missing required 'organizationalUnit'"
            )

    missing_mandatory = MANDATORY_ACCOUNT_NAMES - account_names
    if missing_mandatory:
        missing_str = ", ".join(sorted(missing_mandatory))
        raise LzaError(
            f"accounts-config.yaml is missing required mandatory accounts: {missing_str}"
        )


def _validate_network_config(data: dict[str, Any]) -> None:
    expected_keys = {
        "vpcs",
        "transitGateways",
        "endpointPolicies",
        "defaultVpc",
        "dhcpOpts",
        "prefixes",
        "customerGateways",
    }
    if not any(key in data for key in expected_keys):
        keys_str = ", ".join(sorted(expected_keys))
        raise LzaError(f"network-config.yaml must define at least one network section ({keys_str})")


def _validate_security_config(data: dict[str, Any]) -> None:
    expected_keys = {
        "centralSecurityServices",
        "iamPasswordPolicy",
        "awsConfig",
        "accessAnalyzer",
        "keyManagementService",
        "cloudWatch",
        "snsSubscriptions",
        "guardduty",
        "securityHub",
        "macie",
    }
    if not any(key in data for key in expected_keys):
        keys_str = ", ".join(sorted(expected_keys))
        raise LzaError(
            f"security-config.yaml must define at least one security section ({keys_str})"
        )


def _validate_iam_config(data: dict[str, Any]) -> None:
    expected_keys = {
        "providers",
        "policySets",
        "roleSets",
        "groupSets",
        "userSets",
        "identityCenter",
        "samlProviders",
    }
    if not any(key in data for key in expected_keys):
        keys_str = ", ".join(sorted(expected_keys))
        raise LzaError(
            f"iam-config.yaml must define at least one IAM section ({keys_str})"
        )


def _validate_version_compatibility(
    version: str,
    parsed_files: dict[str, Any],
) -> None:
    """Perform version-specific checks against known LZA features."""
    if version == "latest":
        return

    # Check version format vX.Y.Z
    if not re.match(r"^v\d+(\.\d+)*$", version):
        raise LzaError(
            f"Invalid LZA version format: '{version}'. Expected format 'vX.Y.Z' or 'latest'."
        )
