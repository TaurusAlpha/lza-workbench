"""AWS infrastructure adapter package."""

from lza_workbench.infrastructure.aws.errors import (
    AwsErrorCategory,
    AwsErrorInfo,
    ObservationOutcome,
    classify_aws_error,
    classify_observation_outcome,
    outcome_from_aws_error,
)
from lza_workbench.infrastructure.aws.session import (
    AwsClientFactory,
    AwsExecutionContext,
    resolve_aws_execution_context,
)

__all__ = [
    "AwsClientFactory",
    "AwsErrorCategory",
    "AwsErrorInfo",
    "AwsExecutionContext",
    "ObservationOutcome",
    "classify_aws_error",
    "classify_observation_outcome",
    "outcome_from_aws_error",
    "resolve_aws_execution_context",
]
