"""AWS CloudFormation service adapter for stack operations."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from lza_workbench.aws.client_factory import AwsClientFactory
from lza_workbench.errors import LzaError


@dataclass
class CfnDeploymentPlanResult:
    """Result of CloudFormation stack parameter inspection."""

    stack_name: str
    operation: str  # CREATE, UPDATE, NO_CHANGE, UNKNOWN
    stack_status: str | None
    resolved_parameters: dict[str, str]
    parameter_diffs: dict[str, tuple[str, str]] = field(default_factory=dict)


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


def _is_stack_not_found(exc: Exception) -> bool:
    """Check if an AWS exception indicates that the CloudFormation stack does not exist."""
    if isinstance(exc, ClientError):
        error = exc.response.get("Error", {})
        code = error.get("Code", "")
        message = error.get("Message", "") or str(exc)
        if code in {"StackNotFoundException", "ResourceNotFoundException", "404"}:
            return True
        if code == "ValidationError" and "does not exist" in message.lower():
            return True
    return False


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
    """Inspect CloudFormation stack parameters and compare with desired parameters."""
    clean_stack_name = (stack_name or "").strip()
    if not clean_stack_name:
        return CfnDeploymentPlanResult(
            stack_name="",
            operation="UNKNOWN",
            stack_status="Stack name is required",
            resolved_parameters=resolved_parameters,
        )

    cfn = _get_cfn_client(factory=factory, client=client)
    if cfn is None:
        return CfnDeploymentPlanResult(
            stack_name=clean_stack_name,
            operation="CREATE",
            stack_status=None,
            resolved_parameters=resolved_parameters,
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
        )

    except ClientError as exc:
        if _is_stack_not_found(exc):
            return CfnDeploymentPlanResult(
                stack_name=clean_stack_name,
                operation="CREATE",
                stack_status=None,
                resolved_parameters=resolved_parameters,
            )
        return CfnDeploymentPlanResult(
            stack_name=clean_stack_name,
            operation="UNKNOWN",
            stack_status=f"Error: {exc}",
            resolved_parameters=resolved_parameters,
        )
    except BotoCoreError as exc:
        return CfnDeploymentPlanResult(
            stack_name=clean_stack_name,
            operation="UNKNOWN",
            stack_status=f"Connection failure: {exc}",
            resolved_parameters=resolved_parameters,
        )


def get_cloudformation_stack_status(
    *,
    factory: AwsClientFactory | None = None,
    client: Any | None = None,
    stack_name: str,
) -> CfnStackStatusResult:
    """Get CloudFormation stack status, parameters, and outputs without mutating AWS."""
    clean_stack_name = (stack_name or "").strip()
    if not clean_stack_name:
        return CfnStackStatusResult(
            stack_name="",
            exists=False,
            stack_status="NOT_SPECIFIED",
            error="Stack name is empty",
        )

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
        if _is_stack_not_found(exc):
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
    template_body: str | None = None,
    template_url: str | None = None,
    parameters: dict[str, str],
    operation: str,
    capabilities: list[str] | None = None,
) -> str | None:
    """Trigger CloudFormation stack creation or update.

    Returns the stack ID returned by CloudFormation, or ``None`` when an update is unchanged.
    """
    clean_stack_name = (stack_name or "").strip()
    if not clean_stack_name:
        raise LzaError("Stack name must not be empty")

    cfn = _get_cfn_client(factory=factory, client=client)
    if cfn is None:
        raise LzaError("AWS CloudFormation client is not available")

    if not template_body and not template_url:
        raise LzaError(
            "Either template_body or template_url must be provided for CloudFormation deployment."
        )

    cfn_params = [{"ParameterKey": k, "ParameterValue": v} for k, v in parameters.items()]
    resolved_capabilities = (
        capabilities
        if capabilities is not None
        else ["CAPABILITY_NAMED_IAM", "CAPABILITY_AUTO_EXPAND"]
    )

    kwargs: dict[str, Any] = {
        "StackName": clean_stack_name,
        "Parameters": cfn_params,
        "Capabilities": resolved_capabilities,
    }
    if template_url:
        kwargs["TemplateURL"] = template_url
    elif template_body:
        kwargs["TemplateBody"] = template_body

    try:
        if operation == "CREATE":
            response = cfn.create_stack(**kwargs)
            return str(response.get("StackId", clean_stack_name))
        if operation == "UPDATE":
            response = cfn.update_stack(**kwargs)
            return str(response.get("StackId", clean_stack_name))
        raise LzaError(f"Unsupported deployment operation: {operation}")
    except ClientError as exc:
        error = exc.response.get("Error", {})
        message = error.get("Message", str(exc))
        if operation == "UPDATE" and "no updates are to be performed" in message.lower():
            return None
        raise LzaError(
            f"CloudFormation stack {operation.lower()} failed for '{clean_stack_name}': {message}"
        ) from exc
    except BotoCoreError as exc:
        raise LzaError(
            f"CloudFormation stack {operation.lower()} failed for '{clean_stack_name}': {exc}"
        ) from exc


def stream_cloudformation_stack_events(
    *,
    factory: AwsClientFactory | None = None,
    client: Any | None = None,
    stack_name: str,
    poll_interval: float = 3.0,
    max_consecutive_errors: int = 5,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> CfnStackStatusResult:
    """Stream CloudFormation stack events in real-time until stack reaches terminal status."""
    clean_stack_name = (stack_name or "").strip()
    if not clean_stack_name:
        return CfnStackStatusResult(
            stack_name="",
            exists=False,
            stack_status="NOT_SPECIFIED",
            error="Stack name is empty",
        )

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

    consecutive_errors = 0
    last_error: Exception | str | None = None

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
            if status_res.error:
                consecutive_errors += 1
                last_error = status_res.error
                if consecutive_errors >= max_consecutive_errors:
                    raise LzaError(
                        f"CloudFormation event monitoring failed for stack '{clean_stack_name}' "
                        f"after {consecutive_errors} consecutive AWS errors: {last_error}"
                    )
            else:
                consecutive_errors = 0
                last_error = None

                curr_status = status_res.stack_status or ""
                if curr_status in terminal_success or curr_status in terminal_failure:
                    return status_res

        except ClientError as exc:
            if _is_stack_not_found(exc):
                # Stack might have finished deleting or does not exist
                status_res = get_cloudformation_stack_status(
                    client=cfn, stack_name=clean_stack_name
                )
                if (
                    not status_res.exists
                    or status_res.stack_status in terminal_failure
                    or status_res.stack_status in terminal_success
                ):
                    return status_res
            consecutive_errors += 1
            last_error = exc
            if consecutive_errors >= max_consecutive_errors:
                raise LzaError(
                    f"CloudFormation event monitoring failed for stack '{clean_stack_name}' "
                    f"after {consecutive_errors} consecutive AWS errors: {last_error}"
                ) from exc
        except BotoCoreError as exc:
            consecutive_errors += 1
            last_error = exc
            if consecutive_errors >= max_consecutive_errors:
                raise LzaError(
                    f"CloudFormation event monitoring failed for stack '{clean_stack_name}' "
                    f"after {consecutive_errors} consecutive AWS errors: {last_error}"
                ) from exc

        time.sleep(poll_interval)


def delete_cloudformation_stack(
    *,
    factory: AwsClientFactory | None = None,
    client: Any | None = None,
    stack_name: str,
) -> None:
    """Delete a CloudFormation stack and wait for deletion to complete."""
    clean_stack_name = (stack_name or "").strip()
    if not clean_stack_name:
        raise LzaError("Stack name must not be empty")

    cfn = _get_cfn_client(factory=factory, client=client)
    if cfn is None:
        raise LzaError("AWS CloudFormation client is not available")

    try:
        waiter = cfn.get_waiter("stack_delete_complete")
        cfn.delete_stack(StackName=clean_stack_name)
        waiter.wait(StackName=clean_stack_name)
    except ClientError as exc:
        if not _is_stack_not_found(exc):
            raise LzaError(
                f"Failed to delete CloudFormation stack '{clean_stack_name}': {exc}"
            ) from exc


__all__ = [
    "CfnDeploymentPlanResult",
    "CfnStackStatusResult",
    "delete_cloudformation_stack",
    "deploy_cloudformation_stack",
    "get_cloudformation_stack_status",
    "inspect_cloudformation_stack",
    "stream_cloudformation_stack_events",
]
