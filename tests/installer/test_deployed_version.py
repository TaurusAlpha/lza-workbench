"""Tests for live installer-version discovery."""

from __future__ import annotations

from unittest.mock import MagicMock

from botocore.exceptions import ClientError

from lza_workbench.installer.deployed_version import (
    installer_version_parameter_name,
    resolve_deployed_installer_version,
)


def test_installer_version_parameter_name_uses_lza_prefix_rules() -> None:
    assert (
        installer_version_parameter_name("AWSAccelerator", "AWSAccelerator-InstallerStack")
        == "/accelerator/AWSAccelerator-InstallerStack/version"
    )
    assert (
        installer_version_parameter_name("Customer", "AWSAccelerator-InstallerStack")
        == "/Customer/AWSAccelerator-InstallerStack/version"
    )


def test_resolve_deployed_installer_version_prefers_ssm() -> None:
    cfn_client = MagicMock()
    ssm_client = MagicMock()
    ssm_client.get_parameter.return_value = {"Parameter": {"Value": "1.15.5"}}

    version = resolve_deployed_installer_version(
        cfn_client=cfn_client,
        ssm_client=ssm_client,
        stack_name="AWSAccelerator-InstallerStack",
        accelerator_prefix="AWSAccelerator",
    )

    assert version == "v1.15.5"
    cfn_client.get_template.assert_not_called()


def test_resolve_deployed_installer_version_falls_back_to_template_description() -> None:
    cfn_client = MagicMock()
    cfn_client.get_template.return_value = {
        "TemplateBody": (
            '{"Description": "(SO0199) Landing Zone Accelerator on AWS. Version 1.15.5."}'
        )
    }
    ssm_client = MagicMock()
    ssm_client.get_parameter.side_effect = ClientError(
        {"Error": {"Code": "ParameterNotFound", "Message": "not found"}}, "GetParameter"
    )

    version = resolve_deployed_installer_version(
        cfn_client=cfn_client,
        ssm_client=ssm_client,
        stack_name="AWSAccelerator-InstallerStack",
        accelerator_prefix="AWSAccelerator",
    )

    assert version == "v1.15.5"
