"""Tests for AWS CloudFormation integration utilities."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import BotoCoreError, ClientError

from lza_workbench.aws.cloudformation import (
    delete_cloudformation_stack,
    deploy_cloudformation_stack,
    get_cloudformation_stack_status,
    inspect_cloudformation_stack,
    stream_cloudformation_stack_events,
)
from lza_workbench.errors import LzaError


def test_inspect_cloudformation_stack_create() -> None:
    """Test CloudFormation stack inspection when stack does not exist."""
    client = MagicMock()
    client.describe_stacks.side_effect = ClientError(
        {"Error": {"Code": "ValidationError", "Message": "Stack does not exist"}},
        "DescribeStacks",
    )

    res = inspect_cloudformation_stack(
        client=client,
        stack_name="MyStack",
        resolved_parameters={"Param1": "Val1"},
    )

    assert res.operation == "CREATE"
    assert res.stack_status is None


def test_inspect_cloudformation_stack_update_and_no_change() -> None:
    """Test CloudFormation stack inspection for UPDATE vs NO_CHANGE."""
    client = MagicMock()
    client.describe_stacks.return_value = {
        "Stacks": [
            {
                "StackName": "MyStack",
                "StackStatus": "CREATE_COMPLETE",
                "Parameters": [{"ParameterKey": "Param1", "ParameterValue": "OldVal"}],
            }
        ]
    }

    res_update = inspect_cloudformation_stack(
        client=client,
        stack_name="MyStack",
        resolved_parameters={"Param1": "NewVal"},
    )
    assert res_update.operation == "UPDATE"
    assert res_update.parameter_diffs["Param1"] == ("OldVal", "NewVal")

    res_no_change = inspect_cloudformation_stack(
        client=client,
        stack_name="MyStack",
        resolved_parameters={"Param1": "OldVal"},
    )
    assert res_no_change.operation == "NO_CHANGE"
    assert not res_no_change.parameter_diffs


def test_get_cloudformation_stack_status_deployed() -> None:
    """Test get_cloudformation_stack_status when stack exists."""
    client = MagicMock()
    client.describe_stacks.return_value = {
        "Stacks": [
            {
                "StackName": "MyStack",
                "StackId": "arn:aws:cfn:stack/MyStack/123",
                "StackStatus": "CREATE_COMPLETE",
                "Parameters": [{"ParameterKey": "Key1", "ParameterValue": "Val1"}],
                "Outputs": [{"OutputKey": "Out1", "OutputValue": "Val1"}],
            }
        ]
    }

    res = get_cloudformation_stack_status(client=client, stack_name="MyStack")
    assert res.exists is True
    assert res.stack_status == "CREATE_COMPLETE"
    assert res.stack_id == "arn:aws:cfn:stack/MyStack/123"
    assert res.deployed_parameters == {"Key1": "Val1"}
    assert res.outputs == {"Out1": "Val1"}


def test_get_cloudformation_stack_status_not_deployed() -> None:
    """Test get_cloudformation_stack_status when stack does not exist."""
    client = MagicMock()
    client.describe_stacks.side_effect = ClientError(
        {"Error": {"Code": "ValidationError", "Message": "Stack [MyStack] does not exist"}},
        "DescribeStacks",
    )

    res = get_cloudformation_stack_status(client=client, stack_name="MyStack")
    assert res.exists is False
    assert res.stack_status == "NOT_DEPLOYED"


def test_deploy_cloudformation_stack_create_and_update() -> None:
    """Test that deploy_cloudformation_stack creates and updates stacks with parameters."""
    client = MagicMock()
    client.create_stack.return_value = {"StackId": "arn:aws:cfn:stack/created"}
    client.update_stack.return_value = {"StackId": "arn:aws:cfn:stack/updated"}

    # CREATE with template URL
    stack_id_create = deploy_cloudformation_stack(
        client=client,
        stack_name="MyStack",
        template_url="https://s3.amazonaws.com/bucket/template.json",
        parameters={"Param1": "Val1"},
        operation="CREATE",
    )
    assert stack_id_create == "arn:aws:cfn:stack/created"
    client.create_stack.assert_called_once_with(
        StackName="MyStack",
        TemplateURL="https://s3.amazonaws.com/bucket/template.json",
        Parameters=[{"ParameterKey": "Param1", "ParameterValue": "Val1"}],
        Capabilities=["CAPABILITY_NAMED_IAM", "CAPABILITY_AUTO_EXPAND"],
    )

    # UPDATE with template body
    stack_id_update = deploy_cloudformation_stack(
        client=client,
        stack_name="MyStack",
        template_body="{}",
        parameters={"Param1": "Val1"},
        operation="UPDATE",
    )
    assert stack_id_update == "arn:aws:cfn:stack/updated"
    client.update_stack.assert_called_once_with(
        StackName="MyStack",
        TemplateBody="{}",
        Parameters=[{"ParameterKey": "Param1", "ParameterValue": "Val1"}],
        Capabilities=["CAPABILITY_NAMED_IAM", "CAPABILITY_AUTO_EXPAND"],
    )


def test_deploy_cloudformation_stack_invalid_args() -> None:
    """Test deploy_cloudformation_stack validation errors."""
    client = MagicMock()
    with pytest.raises(LzaError, match="Either template_body or template_url must be provided"):
        deploy_cloudformation_stack(
            client=client,
            stack_name="MyStack",
            parameters={},
            operation="CREATE",
        )


def test_stream_cloudformation_stack_events_transient_error_recovery() -> None:
    """Test that transient AWS errors recover within max_consecutive_errors allowance."""
    client = MagicMock()
    client.describe_stack_events.side_effect = [
        BotoCoreError(),
        {
            "StackEvents": [
                {
                    "EventId": "evt-2",
                    "LogicalResourceId": "InstallerStack",
                    "ResourceType": "AWS::CloudFormation::Stack",
                    "ResourceStatus": "CREATE_COMPLETE",
                },
                {
                    "EventId": "evt-1",
                    "LogicalResourceId": "InstallerStack",
                    "ResourceType": "AWS::CloudFormation::Stack",
                    "ResourceStatus": "CREATE_IN_PROGRESS",
                },
            ]
        },
    ]

    client.describe_stacks.return_value = {
        "Stacks": [
            {
                "StackName": "MyStack",
                "StackId": "arn:aws:cfn:stack/MyStack/123",
                "StackStatus": "CREATE_COMPLETE",
            }
        ]
    }

    received_events: list[dict] = []
    res = stream_cloudformation_stack_events(
        client=client,
        stack_name="MyStack",
        poll_interval=0.01,
        max_consecutive_errors=3,
        on_event=received_events.append,
    )

    assert res.exists is True
    assert res.stack_status == "CREATE_COMPLETE"
    assert len(received_events) == 2
    assert received_events[0]["EventId"] == "evt-1"
    assert received_events[1]["EventId"] == "evt-2"


def test_stream_cloudformation_stack_events_persistent_failure_raises() -> None:
    """Test that persistent AWS errors terminate predictably with actionable context."""
    client = MagicMock()
    client.describe_stack_events.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "User is not authorized"}},
        "DescribeStackEvents",
    )

    match_msg = "CloudFormation event monitoring failed for stack 'MyStack'"
    with pytest.raises(LzaError, match=match_msg) as exc_info:
        stream_cloudformation_stack_events(
            client=client,
            stack_name="MyStack",
            poll_interval=0.01,
            max_consecutive_errors=3,
        )

    assert "AccessDenied" in str(exc_info.value)
    assert "3 consecutive AWS errors" in str(exc_info.value)


def test_stream_cloudformation_stack_events_terminal_failure() -> None:
    """Test that terminal failure stack status is returned cleanly."""
    client = MagicMock()
    client.describe_stack_events.return_value = {
        "StackEvents": [
            {
                "EventId": "evt-fail",
                "LogicalResourceId": "InstallerStack",
                "ResourceType": "AWS::CloudFormation::Stack",
                "ResourceStatus": "CREATE_FAILED",
                "ResourceStatusReason": "Resource creation cancelled",
            }
        ]
    }

    client.describe_stacks.return_value = {
        "Stacks": [
            {
                "StackName": "MyStack",
                "StackId": "arn:aws:cfn:stack/MyStack/123",
                "StackStatus": "CREATE_FAILED",
            }
        ]
    }

    res = stream_cloudformation_stack_events(
        client=client,
        stack_name="MyStack",
        poll_interval=0.01,
    )

    assert res.exists is True
    assert res.stack_status == "CREATE_FAILED"


def test_delete_cloudformation_stack() -> None:
    """Test delete_cloudformation_stack waits for stack deletion."""
    client = MagicMock()
    waiter = MagicMock()
    client.get_waiter.return_value = waiter

    delete_cloudformation_stack(client=client, stack_name="MyStack")
    client.delete_stack.assert_called_once_with(StackName="MyStack")
    waiter.wait.assert_called_once_with(StackName="MyStack")


def test_cloudformation_empty_stack_names() -> None:
    """Test handling of empty stack names across cloudformation functions."""
    res_inspect = inspect_cloudformation_stack(stack_name="", resolved_parameters={})
    assert res_inspect.operation == "UNKNOWN"
    assert res_inspect.stack_name == ""

    res_status = get_cloudformation_stack_status(stack_name="")
    assert res_status.exists is False
    assert res_status.error == "Stack name is empty"

    res_stream = stream_cloudformation_stack_events(stack_name="")
    assert res_stream.exists is False
    assert res_stream.error == "Stack name is empty"

    with pytest.raises(LzaError, match="Stack name must not be empty"):
        deploy_cloudformation_stack(
            stack_name="",
            template_body="{}",
            parameters={},
            operation="CREATE",
        )

    with pytest.raises(LzaError, match="Stack name must not be empty"):
        delete_cloudformation_stack(stack_name="")


def test_deploy_cloudformation_stack_custom_capabilities() -> None:
    """Test deploying a stack with custom capabilities."""
    client = MagicMock()
    client.create_stack.return_value = {"StackId": "arn:aws:cfn:stack/created"}

    deploy_cloudformation_stack(
        client=client,
        stack_name="MyCustomStack",
        template_body="{}",
        parameters={},
        operation="CREATE",
        capabilities=["CAPABILITY_IAM"],
    )
    client.create_stack.assert_called_once_with(
        StackName="MyCustomStack",
        TemplateBody="{}",
        Parameters=[],
        Capabilities=["CAPABILITY_IAM"],
    )


def test_inspect_cloudformation_stack_validation_error_not_swallowed() -> None:
    """Non-missing ValidationError is reported as an error, not treated as a missing stack."""
    client = MagicMock()
    client.describe_stacks.side_effect = ClientError(
        {"Error": {"Code": "ValidationError", "Message": "Invalid template syntax"}},
        "DescribeStacks",
    )

    res = inspect_cloudformation_stack(
        client=client,
        stack_name="MyStack",
        resolved_parameters={"Param1": "Val1"},
    )
    assert res.operation == "UNKNOWN"
    assert "Invalid template syntax" in str(res.stack_status)


def test_inspect_cloudformation_stack_preserves_rollback_complete_status() -> None:
    """Stack inspection reports actual ROLLBACK_COMPLETE status without forcing CREATE."""
    client = MagicMock()
    client.describe_stacks.return_value = {
        "Stacks": [
            {
                "StackName": "MyStack",
                "StackStatus": "ROLLBACK_COMPLETE",
                "Parameters": [{"ParameterKey": "Param1", "ParameterValue": "OldVal"}],
            }
        ]
    }

    res = inspect_cloudformation_stack(
        client=client,
        stack_name="MyStack",
        resolved_parameters={"Param1": "NewVal"},
    )
    assert res.operation == "UPDATE"
    assert res.stack_status == "ROLLBACK_COMPLETE"
