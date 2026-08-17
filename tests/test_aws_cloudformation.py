"""Tests for AWS CodeCommit and CloudFormation inspection modules."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import BotoCoreError, ClientError

from lza_workbench.aws.cloudformation import (
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


def test_stream_cloudformation_stack_events_transient_error_recovery() -> None:
    """Test that transient AWS errors recover within max_consecutive_errors allowance."""
    client = MagicMock()

    # First attempt: transient BotoCoreError on describe_stack_events
    # Second attempt: success on describe_stack_events and describe_stacks
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
