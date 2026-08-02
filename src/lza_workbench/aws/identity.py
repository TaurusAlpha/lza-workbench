"""AWS identity checks.

Create authenticated sessions and validate caller identity without mutating AWS.
"""

from __future__ import annotations

import boto3
import typer


def validate_aws_profile(profile: str, region: str) -> dict[str, str]:
    """Validate the selected AWS profile with STS GetCallerIdentity."""
    try:
        session = boto3.Session(profile_name=profile, region_name=region)
        response = session.client("sts").get_caller_identity()
    except Exception as exc:  # noqa: BLE001
        raise typer.BadParameter(f"AWS profile validation failed for {profile}: {exc}") from exc

    return {
        "account": str(response.get("Account", "")),
        "arn": str(response.get("Arn", "")),
        "user_id": str(response.get("UserId", "")),
    }
