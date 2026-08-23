"""Tests for LZA YAML parsing and configuration schema validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from lza_workbench.configuration.validation import (
    REQUIRED_LZA_CONFIG_FILES,
    parse_yaml_file,
    validate_lza_configuration_schema,
    validate_yaml_syntax,
)
from lza_workbench.errors import LzaError


def _write_valid_lza_configs(config_dir: Path) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global-config.yaml").write_text(
        "homeRegion: eu-west-1\nenabledRegions:\n  - eu-west-1\n",
        encoding="utf-8",
    )
    (config_dir / "organization-config.yaml").write_text(
        "enable: true\norganizationalUnits:\n  - name: Security\n",
        encoding="utf-8",
    )
    (config_dir / "accounts-config.yaml").write_text(
        """
mandatoryAccounts:
  - name: Management
    description: Primary account
    email: management@example.com
    organizationalUnit: Root
  - name: LogArchive
    description: Log archive
    email: logarchive@example.com
    organizationalUnit: Security
  - name: Audit
    description: Security audit
    email: audit@example.com
    organizationalUnit: Security
""",
        encoding="utf-8",
    )
    (config_dir / "network-config.yaml").write_text(
        "vpcs: []\ntransitGateways: []\n",
        encoding="utf-8",
    )
    (config_dir / "security-config.yaml").write_text(
        "centralSecurityServices:\n  delegatedAdminAccount: Audit\n",
        encoding="utf-8",
    )


def test_parse_yaml_file_valid(tmp_path: Path) -> None:
    file_path = tmp_path / "valid.yaml"
    file_path.write_text("key: value\nlist:\n  - item1\n", encoding="utf-8")
    data = parse_yaml_file(file_path)
    assert data == {"key": "value", "list": ["item1"]}


def test_parse_yaml_file_invalid_syntax_raises_lza_error(tmp_path: Path) -> None:
    file_path = tmp_path / "invalid.yaml"
    file_path.write_text("key: [unclosed list\n", encoding="utf-8")
    with pytest.raises(LzaError, match="Invalid YAML syntax in 'invalid.yaml'"):
        parse_yaml_file(file_path)


def test_validate_yaml_syntax_all_files(tmp_path: Path) -> None:
    _write_valid_lza_configs(tmp_path)
    parsed = validate_yaml_syntax(tmp_path)
    for req in REQUIRED_LZA_CONFIG_FILES:
        assert req in parsed
        assert isinstance(parsed[req], dict)


def test_validate_lza_configuration_schema_valid(tmp_path: Path) -> None:
    _write_valid_lza_configs(tmp_path)
    # Should not raise
    validate_lza_configuration_schema(tmp_path, lza_version="v1.16.0")


def test_validate_lza_schema_missing_required_file(tmp_path: Path) -> None:
    _write_valid_lza_configs(tmp_path)
    (tmp_path / "global-config.yaml").unlink()
    with pytest.raises(LzaError, match="missing required file: 'global-config.yaml'"):
        validate_lza_configuration_schema(tmp_path)


def test_validate_lza_schema_missing_home_region(tmp_path: Path) -> None:
    _write_valid_lza_configs(tmp_path)
    (tmp_path / "global-config.yaml").write_text(
        "enabledRegions:\n  - eu-west-1\n",
        encoding="utf-8",
    )
    with pytest.raises(LzaError, match="missing required field: 'homeRegion'"):
        validate_lza_configuration_schema(tmp_path)


def test_validate_lza_schema_missing_mandatory_account(tmp_path: Path) -> None:
    _write_valid_lza_configs(tmp_path)
    (tmp_path / "accounts-config.yaml").write_text(
        """
mandatoryAccounts:
  - name: Management
    email: mgmt@example.com
    organizationalUnit: Root
  - name: LogArchive
    email: log@example.com
    organizationalUnit: Security
""",
        encoding="utf-8",
    )
    with pytest.raises(LzaError, match="missing required mandatory accounts: Audit"):
        validate_lza_configuration_schema(tmp_path)


def test_validate_lza_schema_invalid_version_format(tmp_path: Path) -> None:
    _write_valid_lza_configs(tmp_path)
    with pytest.raises(LzaError, match="Invalid LZA version format"):
        validate_lza_configuration_schema(tmp_path, lza_version="not-a-version")
