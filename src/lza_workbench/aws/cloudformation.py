"""AWS CloudFormation integration utilities for LZA installer deployment planning."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from lza_workbench.aws.client_factory import AwsClientFactory


@dataclass
class CfnDeploymentPlanResult:
    """Result of CloudFormation deployment planning inspection."""

    stack_name: str
    operation: str  # CREATE, UPDATE, NO_CHANGE, UNKNOWN
    stack_status: str | None
    resolved_parameters: dict[str, str]
    parameter_diffs: dict[str, tuple[str, str]] = field(default_factory=dict)
    provenance: dict[str, str] = field(default_factory=dict)


@dataclass
class CfnStackStatusResult:
    """Detailed status of a CloudFormation stack."""

    stack_name: str
    exists: bool
    stack_status: str | None = None
    stack_id: str | None = None
    deployed_parameters: dict[str, str] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    creation_time: str | None = None
    last_updated_time: str | None = None
    error: str | None = None


def _get_cfn_client(
    factory: AwsClientFactory | None = None,
    client: Any | None = None,
) -> Any | None:
    if client is not None:
        return client
    if factory is not None:
        return factory.get_client("cloudformation")
    return None


def inspect_cloudformation_stack(
    *,
    factory: AwsClientFactory | None = None,
    client: Any | None = None,
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

    cfn = _get_cfn_client(factory=factory, client=client)
    if cfn is None:
        return CfnDeploymentPlanResult(
            stack_name=clean_stack_name,
            operation="CREATE",
            stack_status=None,
            resolved_parameters=resolved_parameters,
            provenance=provenance,
        )

    try:
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


def get_cloudformation_stack_status(
    *,
    client: Any | None = None,
    factory: AwsClientFactory | None = None,
    stack_name: str,
) -> CfnStackStatusResult:
    """Get CloudFormation stack status, parameters, and outputs without mutating AWS."""
    clean_stack_name = (stack_name or "AWSAccelerator-InstallerStack").strip()

    cfn = _get_cfn_client(factory=factory, client=client)
    if cfn is None:
        return CfnStackStatusResult(
            stack_name=clean_stack_name,
            exists=False,
            stack_status="NOT_CHECKED",
            error="No AWS session available",
        )

    try:
        response = cfn.describe_stacks(StackName=clean_stack_name)
        stacks = response.get("Stacks", [])
        if not stacks:
            return CfnStackStatusResult(
                stack_name=clean_stack_name,
                exists=False,
                stack_status="NOT_DEPLOYED",
            )

        stack = stacks[0]
        stack_status = stack.get("StackStatus")
        stack_id = stack.get("StackId")
        creation_time = str(stack.get("CreationTime")) if stack.get("CreationTime") else None
        last_updated_time = (
            str(stack.get("LastUpdatedTime")) if stack.get("LastUpdatedTime") else None
        )

        existing_param_list = stack.get("Parameters", [])
        deployed_params = {
            p["ParameterKey"]: p.get("ParameterValue", "") for p in existing_param_list
        }

        output_list = stack.get("Outputs", [])
        outputs = {o["OutputKey"]: o.get("OutputValue", "") for o in output_list}

        return CfnStackStatusResult(
            stack_name=clean_stack_name,
            exists=True,
            stack_status=stack_status,
            stack_id=stack_id,
            deployed_parameters=deployed_params,
            outputs=outputs,
            creation_time=creation_time,
            last_updated_time=last_updated_time,
        )

    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")

        if code in {"ValidationError", "404"} or "does not exist" in str(exc):
            return CfnStackStatusResult(
                stack_name=clean_stack_name,
                exists=False,
                stack_status="NOT_DEPLOYED",
            )
        return CfnStackStatusResult(
            stack_name=clean_stack_name,
            exists=False,
            stack_status="UNKNOWN",
            error=str(exc),
        )
    except BotoCoreError as exc:
        return CfnStackStatusResult(
            stack_name=clean_stack_name,
            exists=False,
            stack_status="UNKNOWN",
            error=f"Connection failure: {exc}",
        )
