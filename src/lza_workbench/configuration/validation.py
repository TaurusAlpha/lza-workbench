"""Validation utilities for LZA configuration files and schemas."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from lza_workbench.errors import LzaError
from lza_workbench.installer.versions import normalize_lza_version

REQUIRED_LZA_CONFIG_FILES = (
    "global-config.yaml",
    "organization-config.yaml",
    "accounts-config.yaml",
    "network-config.yaml",
    "security-config.yaml",
)

MANDATORY_ACCOUNT_NAMES = {"Management", "LogArchive", "Audit"}


def parse_yaml_file(file_path: Path) -> Any:
    """Parse a single YAML file and return its data, raising a clean LzaError on syntax error."""
    yaml = YAML(typ="safe")
    try:
        content = file_path.read_text(encoding="utf-8")
        return yaml.load(content)
    except YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
        problem = getattr(exc, "problem", str(exc))
        raise LzaError(f"Invalid YAML syntax in '{file_path.name}'{location}: {problem}") from exc
    except OSError as exc:
        raise LzaError(f"Failed to read configuration file '{file_path}': {exc}") from exc


def validate_yaml_syntax(config_dir: Path) -> dict[str, Any]:
    """Parse and validate YAML syntax for all YAML files in the configuration directory.

    Returns:
        Dictionary mapping relative file paths to parsed data.
    """
    if not config_dir.is_dir():
        raise LzaError(f"Configuration directory does not exist: {config_dir}")

    parsed_files: dict[str, Any] = {}
    yaml_extensions = {".yaml", ".yml"}

    for file_path in sorted(config_dir.rglob("*")):
        if file_path.is_file() and file_path.suffix.lower() in yaml_extensions:
            rel_name = str(file_path.relative_to(config_dir))
            parsed = parse_yaml_file(file_path)
            parsed_files[rel_name] = parsed

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

    # Version-specific checks
    _validate_version_compatibility(normalized_version, parsed_files)


def _validate_global_config(data: dict[str, Any]) -> None:
    if "homeRegion" not in data or not str(data["homeRegion"]).strip():
        raise LzaError("global-config.yaml is missing required field: 'homeRegion'")
    if "enabledRegions" not in data or not isinstance(data["enabledRegions"], list):
        raise LzaError("global-config.yaml must define 'enabledRegions' as a list")
    if not data["enabledRegions"]:
        raise LzaError("global-config.yaml 'enabledRegions' must contain at least one region")


def _validate_organization_config(data: dict[str, Any]) -> None:
    if "organizationalUnits" in data and not isinstance(data["organizationalUnits"], list):
        raise LzaError("organization-config.yaml 'organizationalUnits' must be a list")


def _validate_accounts_config(data: dict[str, Any]) -> None:
    if "mandatoryAccounts" not in data or not isinstance(data["mandatoryAccounts"], list):
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
