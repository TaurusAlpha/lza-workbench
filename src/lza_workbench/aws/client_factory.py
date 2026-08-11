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
    from lza_workbench.core.workspace import AwsConfig


class AwsClientFactory:
    """Factory for creating and managing authenticated AWS boto3 sessions and clients."""

    def __init__(
        self,
        profile: str | None = None,
        region: str | None = None,
        role: str | None = None,
        access_key: str | None = None,
        secret_access_key: str | None = None,
    ) -> None:
        self.profile = (profile or "").strip() or None
        self.role = (role or "").strip() or None
        self.access_key = (access_key or "").strip() or None
        self.secret_access_key = (secret_access_key or "").strip() or None
        self.region = (region or "").strip() or "us-east-1"
        self._session: boto3.Session | None = None
        self._primed: bool = False

    @classmethod
    def from_aws_config(cls, aws_config: AwsConfig) -> AwsClientFactory:
        """Create factory instance from an AwsConfig model."""
        return cls(
            profile=aws_config.profile,
            role=aws_config.role,
            access_key=aws_config.access_key,
            secret_access_key=aws_config.secret_access_key,
            region=aws_config.region,
        )

    def get_session(self) -> boto3.Session:
        """Get or create the cached boto3 Session."""
        if self._session is None:
            kwargs: dict[str, Any] = {}
            if self.profile:
                kwargs["profile_name"] = self.profile
            if self.access_key and self.secret_access_key:
                kwargs["aws_access_key_id"] = self.access_key
                kwargs["aws_secret_access_key"] = self.secret_access_key
            if self.region:
                kwargs["region_name"] = self.region

            base_session = boto3.Session(**kwargs)
            if self.role:
                sts = base_session.client("sts", region_name=self.region)
                assumed_role = sts.assume_role(
                    RoleArn=self.role,
                    RoleSessionName="LZAWorkbenchSession",
                )
                credentials = assumed_role["Credentials"]
                self._session = boto3.Session(
                    aws_access_key_id=credentials["AccessKeyId"],
                    aws_secret_access_key=credentials["SecretAccessKey"],
                    aws_session_token=credentials["SessionToken"],
                    region_name=self.region,
                )
            else:
                self._session = base_session
        return self._session

    def _prime_session_credentials(self) -> None:
        """Warm up assumed-role session credentials using global us-east-1 STS.

        Opt-in regional STS endpoints (e.g. il-central-1) can fail to assume roles directly
        from SSO tokens unless credentials are primed first via global STS (us-east-1).
        """
        if self._primed:
            return
        session = self.get_session()
        try:
            sts_global = session.client("sts", region_name="us-east-1")
            sts_global.get_caller_identity()
            self._primed = True
        except Exception:
            # Fall back if us-east-1 fails
            pass

    def validate_identity(self) -> dict[str, str]:
        """Validate AWS caller identity using STS GetCallerIdentity."""
        auth_descr = self.profile or self.role or self.access_key or "default"
        try:
            self._prime_session_credentials()
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
            raise LzaError(
                f"AWS authentication validation failed for {auth_descr}: {exc}"
            ) from exc

    def get_client(self, service_name: str) -> Any:
        """Create a boto3 client for the specified AWS service."""
        self._prime_session_credentials()
        session = self.get_session()
        return session.client(service_name, region_name=self.region)


def get_aws_session(
    profile: str | None = None,
    region: str | None = None,
    role: str | None = None,
    access_key: str | None = None,
    secret_access_key: str | None = None,
) -> boto3.Session:
    """Obtain a boto3 Session using the centralized factory."""
    factory = AwsClientFactory(
        profile=profile,
        role=role,
        access_key=access_key,
        secret_access_key=secret_access_key,
        region=region,
    )
    return factory.get_session()


def validate_aws_profile(profile: str, region: str) -> dict[str, str]:
    """Validate AWS profile identity using the centralized factory."""
    factory = AwsClientFactory(profile=profile, region=region)
    return factory.validate_identity()


def validate_aws_credentials(aws_config: AwsConfig) -> dict[str, str]:
    """Validate AWS identity for an AwsConfig using the centralized factory."""
    factory = AwsClientFactory.from_aws_config(aws_config)
    return factory.validate_identity()
