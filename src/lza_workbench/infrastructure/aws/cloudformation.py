"""AWS CloudFormation service adapter for stack operations."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from lza_workbench.errors import LzaError
from lza_workbench.infrastructure.aws.errors import classify_aws_error


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
    return classify_aws_error(exc).is_not_found


def inspect_cloudformation_stack(
    *,
    client: Any,
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

    try:
        response = client.describe_stacks(StackName=clean_stack_name)
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

    except Exception as exc:
        info = classify_aws_error(exc)
        if info.is_not_found:
            return CfnDeploymentPlanResult(
                stack_name=clean_stack_name,
                operation="CREATE",
                stack_status=None,
                resolved_parameters=resolved_parameters,
            )
        prefix = "Connection failure" if info.is_unavailable else "Error"
        return CfnDeploymentPlanResult(
            stack_name=clean_stack_name,
            operation="UNKNOWN",
            stack_status=f"{prefix}: {info.message}",
            resolved_parameters=resolved_parameters,
        )


def get_cloudformation_stack_status(
    *,
    client: Any,
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

    try:
        response = client.describe_stacks(StackName=clean_stack_name)
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

    except Exception as exc:
        info = classify_aws_error(exc)
        if info.is_not_found:
            return CfnStackStatusResult(
                stack_name=clean_stack_name,
                exists=False,
                stack_status="NOT_DEPLOYED",
            )
        prefix = "Connection failure: " if info.is_unavailable else ""
        return CfnStackStatusResult(
            stack_name=clean_stack_name,
            exists=False,
            stack_status="UNKNOWN",
            error=f"{prefix}{info.message}",
        )


def get_cloudformation_stack_template(
    *,
    client: Any,
    stack_name: str,
) -> str | None:
    """Return a deployed stack template body when it can be read."""
    clean_stack_name = (stack_name or "").strip()
    if not clean_stack_name:
        return None

    try:
        template_body = client.get_template(
            StackName=clean_stack_name, TemplateStage="Original"
        ).get("TemplateBody")
        if isinstance(template_body, str):
            return template_body
        if isinstance(template_body, Mapping):
            return json.dumps(template_body, indent=2) + "\n"
        return None
    except (ClientError, BotoCoreError):
        return None


def deploy_cloudformation_stack(
    *,
    client: Any,
    stack_name: str,
    template_body: str | None = None,
    template_url: str | None = None,
    parameters: dict[str, str],
    operation: str,
    capabilities: list[str] | None = None,
) -> str:
    """Trigger CloudFormation stack creation or update.

    Returns the stack ID returned by CloudFormation, or ``None`` when an update is unchanged.
    """
    clean_stack_name = (stack_name or "").strip()
    if not clean_stack_name:
        raise LzaError("Stack name must not be empty")

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
            response = client.create_stack(**kwargs)
            return str(response.get("StackId", clean_stack_name))
        if operation == "UPDATE":
            response = client.update_stack(**kwargs)
            return str(response.get("StackId", clean_stack_name))
        raise LzaError(f"Unsupported deployment operation: {operation}")
    except ClientError as exc:
        error = exc.response.get("Error", {})
        message = error.get("Message", str(exc))
        if operation == "UPDATE" and "no updates are to be performed" in message.lower():
            return str(
                client.describe_stacks(StackName=clean_stack_name)
                .get("Stacks", [{}])[0]
                .get("StackId")
            )
        raise LzaError(
            f"CloudFormation stack {operation.lower()} failed for '{clean_stack_name}': {message}"
        ) from exc
    except BotoCoreError as exc:
        raise LzaError(
            f"CloudFormation stack {operation.lower()} failed for '{clean_stack_name}': {exc}"
        ) from exc


def _dispatch_new_stack_events(
    events: list[dict[str, Any]],
    seen_event_ids: set[str],
    on_event: Callable[[dict[str, Any]], None] | None,
) -> None:
    for evt in reversed(events):
        evt_id = evt.get("EventId")
        if evt_id and evt_id not in seen_event_ids:
            seen_event_ids.add(evt_id)
            if on_event:
                on_event(evt)


def _handle_monitoring_error(
    error: Exception | str,
    consecutive_errors: int,
    max_consecutive_errors: int,
    clean_stack_name: str,
) -> int:
    consecutive_errors += 1
    if consecutive_errors >= max_consecutive_errors:
        raise LzaError(
            f"CloudFormation event monitoring failed for stack '{clean_stack_name}' "
            f"after {consecutive_errors} consecutive AWS errors: {error}"
        ) from (error if isinstance(error, Exception) else None)
    return consecutive_errors


def stream_cloudformation_stack_events(
    *,
    client: Any,
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

    seen_event_ids: set[str] = set()
    terminal_statuses = {
        "CREATE_COMPLETE",
        "UPDATE_COMPLETE",
        "CREATE_FAILED",
        "ROLLBACK_COMPLETE",
        "UPDATE_ROLLBACK_COMPLETE",
        "ROLLBACK_FAILED",
        "UPDATE_ROLLBACK_FAILED",
        "DELETE_COMPLETE",
        "DELETE_FAILED",
    }

    consecutive_errors = 0

    while True:
        try:
            events_resp = client.describe_stack_events(StackName=clean_stack_name)
            _dispatch_new_stack_events(events_resp.get("StackEvents", []), seen_event_ids, on_event)

            status_res = get_cloudformation_stack_status(client=client, stack_name=clean_stack_name)
            if status_res.error:
                consecutive_errors = _handle_monitoring_error(
                    status_res.error, consecutive_errors, max_consecutive_errors, clean_stack_name
                )
            else:
                consecutive_errors = 0
                if (status_res.stack_status or "") in terminal_statuses:
                    return status_res

        except ClientError as exc:
            if _is_stack_not_found(exc):
                status_res = get_cloudformation_stack_status(
                    client=client, stack_name=clean_stack_name
                )
                if not status_res.exists or status_res.stack_status in terminal_statuses:
                    return status_res
            consecutive_errors = _handle_monitoring_error(
                exc, consecutive_errors, max_consecutive_errors, clean_stack_name
            )
        except BotoCoreError as exc:
            consecutive_errors = _handle_monitoring_error(
                exc, consecutive_errors, max_consecutive_errors, clean_stack_name
            )

        time.sleep(poll_interval)


def delete_cloudformation_stack(
    *,
    client: Any,
    stack_name: str,
) -> None:
    """Delete a CloudFormation stack and wait for deletion to complete."""
    clean_stack_name = (stack_name or "").strip()
    if not clean_stack_name:
        raise LzaError("Stack name must not be empty")

    try:
        waiter = client.get_waiter("stack_delete_complete")
        client.delete_stack(StackName=clean_stack_name)
        waiter.wait(StackName=clean_stack_name)
    except (ClientError, BotoCoreError) as exc:
        if isinstance(exc, ClientError) and _is_stack_not_found(exc):
            return
        raise LzaError(
            f"Failed to delete CloudFormation stack '{clean_stack_name}': {exc}"
        ) from exc


def disable_stack_termination_protection(
    *,
    client: Any,
    stack_name: str,
) -> None:
    """Disable CloudFormation termination protection for a stack."""
    clean_stack_name = (stack_name or "").strip()
    if not clean_stack_name:
        raise LzaError("Stack name must not be empty")

    try:
        client.update_termination_protection(
            EnableTerminationProtection=False,
            StackName=clean_stack_name,
        )
    except (ClientError, BotoCoreError) as exc:
        raise LzaError(
            f"Failed to disable termination protection for stack '{clean_stack_name}': {exc}"
        ) from exc


def get_retained_logical_ids(
    *,
    client: Any,
    stack_name: str,
) -> set[str]:
    """Identify logical resource IDs configured with DeletionPolicy: Retain."""
    clean_stack_name = (stack_name or "").strip()
    if not clean_stack_name:
        return set()

    retained_ids: set[str] = set()
    try:
        resp = client.get_template(StackName=clean_stack_name)
        template_body = resp.get("TemplateBody")
        template_data = None

        if isinstance(template_body, str):
            try:
                template_data = json.loads(template_body)
            except Exception:
                template_data = None
        elif isinstance(template_body, Mapping):
            template_data = template_body

        if isinstance(template_data, Mapping):
            resources = template_data.get("Resources", {})
            if isinstance(resources, Mapping):
                for logical_id, resource_def in resources.items():
                    if isinstance(resource_def, Mapping):
                        policy = resource_def.get("DeletionPolicy")
                        if policy in ("Retain", "RetainExceptOnCreate"):
                            retained_ids.add(str(logical_id))
        elif isinstance(template_body, str):
            pattern = re.compile(
                r"(\w+):\s*\n(?:[ \t]+[^\n]+\n)*?[ \t]+DeletionPolicy:\s*['\"]?Retain"
            )
            for match in pattern.finditer(template_body):
                retained_ids.add(match.group(1))
    except (ClientError, BotoCoreError):
        pass

    return retained_ids


def get_stack_resources(
    *,
    client: Any,
    stack_name: str,
) -> list[dict[str, Any]]:
    """Retrieve physical resources associated with a stack, tagging retained resources."""
    clean_stack_name = (stack_name or "").strip()
    if not clean_stack_name:
        return []

    retained_ids = get_retained_logical_ids(client=client, stack_name=clean_stack_name)
    resources: list[dict[str, Any]] = []

    try:
        paginator = client.get_paginator("list_stack_resources")
        for page in paginator.paginate(StackName=clean_stack_name):
            for res in page.get("StackResourceSummaries", []):
                logical_id = str(res.get("LogicalResourceId", ""))
                is_retained = logical_id in retained_ids
                resources.append(
                    {
                        "LogicalResourceId": logical_id,
                        "PhysicalResourceId": res.get("PhysicalResourceId"),
                        "ResourceType": res.get("ResourceType"),
                        "ResourceStatus": res.get("ResourceStatus"),
                        "DeletionPolicy": "Retain" if is_retained else "Delete",
                        "IsRetained": is_retained,
                    }
                )
    except (ClientError, BotoCoreError):
        pass

    return resources


def list_matching_stacks(
    *,
    client: Any,
    prefix: str,
    account_id: str | None = None,
    region: str | None = None,
) -> list[dict[str, Any]]:
    """List deployed CloudFormation stacks matching accelerator prefix."""
    clean_prefix = (prefix or "").strip()
    if not clean_prefix:
        return []

    prefix_with_hyphen = f"{clean_prefix}-" if not clean_prefix.endswith("-") else clean_prefix

    all_stacks: list[dict[str, Any]] = []
    try:
        paginator = client.get_paginator("describe_stacks")
        for page in paginator.paginate():
            for s in page.get("Stacks", []):
                name = s.get("StackName", "")
                if s.get("StackStatus") == "DELETE_COMPLETE":
                    continue
                if name.startswith(prefix_with_hyphen) or name == clean_prefix:
                    all_stacks.append(s)
    except (ClientError, BotoCoreError) as exc:
        raise LzaError(f"Failed to list CloudFormation stacks: {exc}") from exc

    return all_stacks


__all__ = [
    "CfnDeploymentPlanResult",
    "CfnStackStatusResult",
    "delete_cloudformation_stack",
    "deploy_cloudformation_stack",
    "disable_stack_termination_protection",
    "get_cloudformation_stack_status",
    "get_cloudformation_stack_template",
    "get_retained_logical_ids",
    "get_stack_resources",
    "inspect_cloudformation_stack",
    "list_matching_stacks",
    "stream_cloudformation_stack_events",
]

