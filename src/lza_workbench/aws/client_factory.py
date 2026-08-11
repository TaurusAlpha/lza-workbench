"""Centralized AWS session and client factory for LZA Workbench."""

from __future__ import annotations

from typing import Any

import boto3
import typer

from lza_workbench.utils.output import (
    print_info,
    print_warning,
)


class AwsClientFactory:
    """Factory for creating and managing authenticated AWS boto3 sessions and clients."""

    def __init__(self, profile: str | None = None, region: str | None = None) -> None:
        self.profile = (profile or "").strip() or None
        self.region = (region or "").strip() or "us-east-1"
        self._session: boto3.Session | None = None
        self._primed: bool = False

    def get_session(self) -> boto3.Session:
        """Get or create the cached boto3 Session."""
        if self._session is None:
            kwargs: dict[str, Any] = {}
            if self.profile:
                kwargs["profile_name"] = self.profile
            if self.region:
                kwargs["region_name"] = self.region
            self._session = boto3.Session(**kwargs)
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
        """Validate AWS profile caller identity using STS GetCallerIdentity."""
        profile_name = self.profile or "default"
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
                f"AWS profile validation failed for '{profile_name}'. "
                "AWS operations might be limited."
            )
            print_info(
                message="Run the following command to authenticate:\n"
                f"  aws sso login --profile {profile_name}"
            )
            raise typer.BadParameter(
                f"AWS profile validation failed for {profile_name}: {exc}"
            ) from exc

    def get_client(self, service_name: str) -> Any:
        """Create a boto3 client for the specified AWS service."""
        self._prime_session_credentials()
        session = self.get_session()
        return session.client(service_name, region_name=self.region)


def get_aws_session(profile: str | None = None, region: str | None = None) -> boto3.Session:
    """Obtain a boto3 Session using the centralized factory."""
    factory = AwsClientFactory(profile, region)
    return factory.get_session()


def validate_aws_profile(profile: str, region: str) -> dict[str, str]:
    """Validate AWS profile identity using the centralized factory."""
    factory = AwsClientFactory(profile, region)
    return factory.validate_identity()
