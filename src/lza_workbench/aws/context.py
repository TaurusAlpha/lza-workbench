"""Resolve the AWS execution context shared by command workflows."""

from __future__ import annotations

from dataclasses import dataclass

from lza_workbench.aws.client_factory import AwsClientFactory
from lza_workbench.core.errors import LzaError
from lza_workbench.workspace.models import AwsConfig


@dataclass(frozen=True)
class AwsExecutionContext:
    """Resolved external AWS authentication for one command execution."""

    region: str
    factory: AwsClientFactory
    identity: dict[str, str] | None
    error: str | None


def resolve_aws_execution_context(
    aws_config: AwsConfig,
    *,
    profile_override: str | None = None,
    validate_identity: bool = True,
    require_identity: bool = False,
    require_expected_account: bool = False,
    prime_credentials: bool = False,
) -> AwsExecutionContext:
    """Resolve profile/role/region once and optionally validate the target account."""
    profile = (profile_override or aws_config.profile or "").strip() or None
    resolved_config = aws_config.model_copy(update={"profile": profile})
    factory = AwsClientFactory.from_aws_config(
        resolved_config, prime_credentials=prime_credentials
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
        if aws_config.account_id and identity["account"] != aws_config.account_id:
            raise LzaError(
                "Authenticated AWS account does not match lza-workspace.yaml: "
                f"expected {aws_config.account_id}, received {identity['account']}."
            )

    return AwsExecutionContext(
        region=resolved_config.region,
        factory=factory,
        identity=identity,
        error=error,
    )
