"""Centralized AWS session and execution context for LZA Workbench."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import boto3

from lza_workbench.errors import LzaError


class AwsClientFactory:
    """Factory for creating and managing authenticated AWS boto3 sessions and clients."""

    def __init__(
        self,
        profile: str | None = None,
        region: str | None = None,
        role_arn: str | None = None,
        prime_credentials: bool = False,
    ) -> None:
        self.profile = (profile or "").strip() or None
        self.region = (region or "").strip() or "us-east-1"
        self.role_arn = (role_arn or "").strip() or None
        self.prime_credentials = prime_credentials
        self._session: boto3.Session | None = None
        self._source_session: boto3.Session | None = None
        self._primed: bool = False

    def _get_source_session(self) -> boto3.Session:
        """Get or create the source session before any role assumption."""
        if self._source_session is None:
            kwargs: dict[str, Any] = {}
            if self.profile:
                kwargs["profile_name"] = self.profile
            if self.region:
                kwargs["region_name"] = self.region
            self._source_session = boto3.Session(**kwargs)
        return self._source_session

    def _prime_source_credentials(self) -> None:
        """Optionally prime source session credentials using global us-east-1 STS.

        Opt-in regional STS endpoints (e.g. il-central-1) can fail to assume roles directly
        from SSO tokens unless credentials are primed first via global STS (us-east-1).
        """
        if self._primed:
            return
        source_session = self._get_source_session()
        sts_global = source_session.client("sts", region_name="us-east-1")
        sts_global.get_caller_identity()
        self._primed = True

    def get_session(self) -> boto3.Session:
        if self._session is None:
            source_session = self._get_source_session()

            if self.role_arn:
                if self.prime_credentials:
                    self._prime_source_credentials()

                sts = source_session.client("sts", region_name=self.region)
                session_name = "lza-workbench"
                response = sts.assume_role(
                    RoleArn=self.role_arn,
                    RoleSessionName=session_name,
                )
                creds = response["Credentials"]
                self._session = boto3.Session(
                    aws_access_key_id=creds["AccessKeyId"],
                    aws_secret_access_key=creds["SecretAccessKey"],
                    aws_session_token=creds["SessionToken"],
                    region_name=self.region,
                )
            else:
                self._session = source_session

        return self._session

    def get_client(self, service_name: str) -> Any:
        if service_name == "codeconnections":
            try:
                return self.get_session().client("codeconnections")
            except Exception:
                return self.get_session().client("codestar-connections")
        return self.get_session().client(service_name)

    def for_region(self, region: str) -> AwsClientFactory:
        """Derive a new factory for a different AWS region."""
        return AwsClientFactory(
            profile=self.profile,
            region=region,
            role_arn=self.role_arn,
            prime_credentials=self.prime_credentials,
        )

    def for_profile(self, profile: str, region: str | None = None) -> AwsClientFactory:
        """Derive a new factory for a specific AWS profile."""
        return AwsClientFactory(
            profile=profile,
            region=region or self.region,
            prime_credentials=self.prime_credentials,
        )

    def for_account(
        self,
        account_id: str,
        role_name: str,
        region: str | None = None,
    ) -> AwsClientFactory:
        """Derive a new factory targeting a member account by assuming a role."""
        target_role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
        return AwsClientFactory(
            profile=self.profile,
            region=region or self.region,
            role_arn=target_role_arn,
            prime_credentials=self.prime_credentials,
        )


    def validate_identity(self) -> dict[str, str]:
        """Validate external AWS credentials and return caller identity."""
        auth_descr = self.role_arn or self.profile or "default"
        try:
            if not self.role_arn and self.prime_credentials:
                self._prime_source_credentials()
            session = self.get_session()
            sts = session.client("sts", region_name=self.region)
            response = sts.get_caller_identity()
            return {
                "account": str(response.get("Account", "")),
                "arn": str(response.get("Arn", "")),
                "user_id": str(response.get("UserId", "")),
            }
        except Exception as exc:
            msg = f"AWS authentication validation failed for '{auth_descr}': {exc}."
            if self.profile:
                msg += f" Run 'aws sso login --profile {self.profile}' to authenticate."
            raise LzaError(msg) from exc


@dataclass(frozen=True)
class AwsExecutionContext:
    """Resolved external AWS authentication for one command execution."""

    region: str
    factory: AwsClientFactory
    identity: dict[str, str] | None
    error: str | None

    @property
    def is_live(self) -> bool:
        """Return True if AWS identity was successfully validated."""
        return self.identity is not None


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


__all__ = [
    "AwsClientFactory",
    "AwsExecutionContext",
    "resolve_aws_execution_context",
]
