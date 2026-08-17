"""Centralized AWS session and client factory for LZA Workbench."""

from __future__ import annotations

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
        """Get or create the authenticated boto3 session."""
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
        """Create a service client using the authenticated session."""
        return self.get_session().client(service_name)

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
