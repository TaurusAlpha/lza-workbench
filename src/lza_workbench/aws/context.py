"""Resolve the AWS execution context shared by command workflows."""

from __future__ import annotations

from dataclasses import dataclass

from lza_workbench.aws.client_factory import AwsClientFactory
from lza_workbench.errors import LzaError


@dataclass(frozen=True)
class AwsExecutionContext:
    """Resolved external AWS authentication for one command execution."""

    region: str
    factory: AwsClientFactory
    identity: dict[str, str] | None
    error: str | None


def resolve_aws_execution_context(
    *,
    profile: str | None = None,
    region: str = "us-east-1",
    role_arn: str | None = None,
    expected_account_id: str | None = None,
    profile_override: str | None = None,
    validate_identity: bool = True,
    require_identity: bool = False,
    require_expected_account: bool = False,
    prime_credentials: bool = False,
) -> AwsExecutionContext:
    """Resolve profile/role/region once and optionally validate the target account."""
    resolved_profile = (profile_override or profile or "").strip() or None
    resolved_region = (region or "").strip() or "us-east-1"
    resolved_role_arn = (role_arn or "").strip() or None

    factory = AwsClientFactory(
        profile=resolved_profile,
        region=resolved_region,
        role_arn=resolved_role_arn,
        prime_credentials=prime_credentials,
    )
    identity: dict[str, str] | None = None
    error: str | None = None

    if validate_identity:
        try:
            identity = factory.validate_identity()
        except LzaError as exc:
            error = str(exc)
            if require_identity:
                raise

    if require_expected_account:
        if identity is None:
            raise LzaError("AWS identity validation is required before mutating AWS resources.")
        if expected_account_id and identity["account"] != expected_account_id:
            raise LzaError(
                "Authenticated AWS account does not match lza-workspace.yaml: "
                f"expected {expected_account_id}, received {identity['account']}."
            )

    return AwsExecutionContext(
        region=resolved_region,
        factory=factory,
        identity=identity,
        error=error,
    )
