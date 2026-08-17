"""Centralized AWS session and client factory for LZA Workbench."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import boto3

from lza_workbench.core.errors import LzaError
from lza_workbench.utils.output import (
    print_info,
    print_warning,
)

if TYPE_CHECKING:
    from lza_workbench.workspace.models import AwsConfig


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

    @classmethod
    def from_aws_config(
        cls, aws_config: AwsConfig, prime_credentials: bool = False
    ) -> AwsClientFactory:
        """Create factory instance from an AwsConfig model."""
        return cls(
            profile=aws_config.profile,
            region=aws_config.region,
            role_arn=aws_config.role_arn,
            prime_credentials=prime_credentials,
        )

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
        if self._primed or not self.prime_credentials:
            return
        source_session = self._get_source_session()
        try:
            sts_global = source_session.client("sts", region_name="us-east-1")
            sts_global.get_caller_identity()
            self._primed = True
        except Exception:
            # Fall back if us-east-1 priming fails
            pass

    def get_session(self) -> boto3.Session:
        """Get or create the cached boto3 Session."""
        if self._session is None:
            source_session = self._get_source_session()
            if not self.role_arn:
                self._session = source_session
            else:
                if self.prime_credentials:
                    self._prime_source_credentials()
                sts = source_session.client("sts", region_name=self.region)
                response = sts.assume_role(
                    RoleArn=self.role_arn,
                    RoleSessionName="lza-workbench",
                )
                credentials = response["Credentials"]
                self._session = boto3.Session(
                    aws_access_key_id=credentials["AccessKeyId"],
                    aws_secret_access_key=credentials["SecretAccessKey"],
                    aws_session_token=credentials["SessionToken"],
                    region_name=self.region,
                )

        return self._session

    def validate_identity(self) -> dict[str, str]:
        """Validate AWS caller identity using STS GetCallerIdentity."""
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
            print_warning(
                f"AWS authentication validation failed for '{auth_descr}'. "
                "AWS operations might be limited."
            )
            if self.profile:
                print_info(
                    message="Run the following command to authenticate:\n"
                    f"  aws sso login --profile {self.profile}"
                )
            raise LzaError(f"AWS authentication validation failed for {auth_descr}: {exc}") from exc

    def get_client(self, service_name: str) -> Any:
        """Create a boto3 client for the specified AWS service."""
        session = self.get_session()
        return session.client(service_name, region_name=self.region)
