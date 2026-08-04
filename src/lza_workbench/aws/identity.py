"""AWS identity checks.

Create authenticated sessions and validate caller identity without mutating AWS.
"""

from __future__ import annotations

import boto3
import typer


def get_aws_session(profile: str | None = None, region: str | None = None) -> boto3.Session:
    """Create a boto3 Session with optional profile and region kwargs."""
    kwargs = {}
    if profile:
        kwargs["profile_name"] = profile
    if region:
        kwargs["region_name"] = region
    return boto3.Session(**kwargs)


def validate_aws_profile(profile: str, region: str) -> dict[str, str]:
    """Validate the selected AWS profile with STS GetCallerIdentity."""
    try:
        session = get_aws_session(profile, region)
        response = session.client("sts").get_caller_identity()
    except Exception as exc:  # noqa: BLE001
        raise typer.BadParameter(f"AWS profile validation failed for {profile}: {exc}") from exc

    return {
        "account": str(response.get("Account", "")),
        "arn": str(response.get("Arn", "")),
        "user_id": str(response.get("UserId", "")),
    }
