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


def deploy_cloudformation_stack(
    *,
    factory: AwsClientFactory | None = None,
    client: Any | None = None,
    stack_name: str,
    template_body: str,
    parameters: dict[str, str],
    operation: str,
) -> str:
    """Trigger CloudFormation stack creation or update.

    Returns the stack ID returned by CloudFormation.
    """
    clean_stack_name = (stack_name or "AWSAccelerator-InstallerStack").strip()
    cfn = _get_cfn_client(factory=factory, client=client)
    if cfn is None:
        raise ValueError("AWS CloudFormation client is not available")

    cfn_params = [{"ParameterKey": k, "ParameterValue": v} for k, v in parameters.items()]
    capabilities = ["CAPABILITY_NAMED_IAM", "CAPABILITY_AUTO_EXPAND"]

    if operation == "CREATE":
        response = cfn.create_stack(
            StackName=clean_stack_name,
            TemplateBody=template_body,
            Parameters=cfn_params,
            Capabilities=capabilities,
        )
        return str(response.get("StackId", clean_stack_name))
    elif operation == "UPDATE":
        response = cfn.update_stack(
            StackName=clean_stack_name,
            TemplateBody=template_body,
            Parameters=cfn_params,
            Capabilities=capabilities,
        )
        return str(response.get("StackId", clean_stack_name))
    else:
        raise ValueError(f"Unsupported deployment operation: {operation}")


def stream_cloudformation_stack_events(
    *,
    factory: AwsClientFactory | None = None,
    client: Any | None = None,
    stack_name: str,
    poll_interval: float = 3.0,
    on_event: Any | None = None,
) -> CfnStackStatusResult:
    """Stream CloudFormation stack events in real-time until stack reaches terminal status."""
    import time

    clean_stack_name = (stack_name or "AWSAccelerator-InstallerStack").strip()
    cfn = _get_cfn_client(factory=factory, client=client)
    if cfn is None:
        return CfnStackStatusResult(
            stack_name=clean_stack_name,
            exists=False,
            stack_status="NOT_CHECKED",
            error="No AWS session available",
        )

    seen_event_ids: set[str] = set()

    terminal_success = {"CREATE_COMPLETE", "UPDATE_COMPLETE"}
    terminal_failure = {
        "CREATE_FAILED",
        "ROLLBACK_COMPLETE",
        "UPDATE_ROLLBACK_COMPLETE",
        "ROLLBACK_FAILED",
        "UPDATE_ROLLBACK_FAILED",
        "DELETE_COMPLETE",
        "DELETE_FAILED",
    }

    while True:
        try:
            events_resp = cfn.describe_stack_events(StackName=clean_stack_name)
            events = events_resp.get("StackEvents", [])
            # Sort events chronologically (oldest first)
            events.reverse()

            for evt in events:
                evt_id = evt.get("EventId")
                if evt_id and evt_id not in seen_event_ids:
                    seen_event_ids.add(evt_id)
                    if on_event:
                        on_event(evt)

            status_res = get_cloudformation_stack_status(client=cfn, stack_name=clean_stack_name)
            curr_status = status_res.stack_status or ""

            if curr_status in terminal_success or curr_status in terminal_failure:
                return status_res

        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"ValidationError", "404"} or "does not exist" in str(exc):
                # Stack might have finished deleting or not exist
                return get_cloudformation_stack_status(client=cfn, stack_name=clean_stack_name)
        except BotoCoreError:
            pass

        time.sleep(poll_interval)

