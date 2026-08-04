"""AWS CloudFormation integration utilities for LZA installer deployment planning."""

from __future__ import annotations

from dataclasses import dataclass, field

import boto3
from botocore.exceptions import BotoCoreError, ClientError


@dataclass
class CfnDeploymentPlanResult:
    """Result of CloudFormation deployment planning inspection."""

    stack_name: str
    operation: str  # CREATE, UPDATE, NO_CHANGE, UNKNOWN
    stack_status: str | None
    resolved_parameters: dict[str, str]
    parameter_diffs: dict[str, tuple[str, str]] = field(default_factory=dict)
    provenance: dict[str, str] = field(default_factory=dict)


def inspect_cloudformation_stack(
    *,
    session: boto3.Session | None,
    stack_name: str,
    resolved_parameters: dict[str, str],
) -> CfnDeploymentPlanResult:
    """Inspect CloudFormation stack to determine deployment operation without mutating AWS."""
    clean_stack_name = (stack_name or "AWSAccelerator-InstallerStack").strip()

    provenance = {
        "RepositorySource": "installer.source_code.repository_type",
        "RepositoryOwner": "installer.source_code.owner",
        "RepositoryName": "installer.source_code.repository_name",
        "RepositoryBranchName": "installer.source_code.branch / lza.version",
        "ManagementAccountEmail": "installer.options.management_account_email",
        "LogArchiveAccountEmail": "installer.options.log_archive_account_email",
        "AuditAccountEmail": "installer.options.audit_account_email",
        "AcceleratorPrefix": "lza.accelerator_prefix",
        "ConfigurationRepositoryLocation": "configuration.repository.type",
    }

    if not session:
        return CfnDeploymentPlanResult(
            stack_name=clean_stack_name,
            operation="CREATE",
            stack_status=None,
            resolved_parameters=resolved_parameters,
            provenance=provenance,
        )

    try:
        cfn = session.client("cloudformation")
        response = cfn.describe_stacks(StackName=clean_stack_name)
        stacks = response.get("Stacks", [])
        if not stacks:
            return CfnDeploymentPlanResult(
                stack_name=clean_stack_name,
                operation="CREATE",
                stack_status=None,
                resolved_parameters=resolved_parameters,
                provenance=provenance,
            )

        stack = stacks[0]
        stack_status = stack.get("StackStatus")
        existing_param_list = stack.get("Parameters", [])
        existing_params = {
            p["ParameterKey"]: p.get("ParameterValue", "") for p in existing_param_list
        }

        diffs: dict[str, tuple[str, str]] = {}
        for k, v in resolved_parameters.items():
            current_val = existing_params.get(k, "")
            if current_val != v:
                diffs[k] = (current_val, v)

        operation = "UPDATE" if diffs else "NO_CHANGE"

        return CfnDeploymentPlanResult(
            stack_name=clean_stack_name,
            operation=operation,
            stack_status=stack_status,
            resolved_parameters=resolved_parameters,
            parameter_diffs=diffs,
            provenance=provenance,
        )

    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"ValidationError", "404"} or "does not exist" in str(exc):
            return CfnDeploymentPlanResult(
                stack_name=clean_stack_name,
                operation="CREATE",
                stack_status=None,
                resolved_parameters=resolved_parameters,
                provenance=provenance,
            )
        return CfnDeploymentPlanResult(
            stack_name=clean_stack_name,
            operation="UNKNOWN",
            stack_status=f"Error: {exc}",
            resolved_parameters=resolved_parameters,
            provenance=provenance,
        )
    except BotoCoreError as exc:
        return CfnDeploymentPlanResult(
            stack_name=clean_stack_name,
            operation="UNKNOWN",
            stack_status=f"Connection failure: {exc}",
            resolved_parameters=resolved_parameters,
            provenance=provenance,
        )
