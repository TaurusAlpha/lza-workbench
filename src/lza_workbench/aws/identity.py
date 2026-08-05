"""AWS identity checks.

Create authenticated sessions and validate caller identity without mutating AWS.
"""

from __future__ import annotations

from lza_workbench.aws.client_factory import (
    AwsClientFactory,
    get_aws_session,
    validate_aws_profile,
)

__all__ = ["AwsClientFactory", "get_aws_session", "validate_aws_profile"]
