"""Thin AWS IAM service adapter."""

from __future__ import annotations

from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from lza_workbench.errors import LzaError


def delete_role(
    *,
    client: Any,
    role_name: str,
) -> None:
    """Detach attached and inline policies, then delete an IAM role."""
    clean_name = (role_name or "").strip()
    if not clean_name:
        raise LzaError("IAM Role name must not be empty")

    try:
        # Detach managed policies
        attached = client.list_attached_role_policies(RoleName=clean_name)
        for pol in attached.get("AttachedPolicies", []):
            client.detach_role_policy(RoleName=clean_name, PolicyArn=pol["PolicyArn"])

        # Delete inline policies
        inline = client.list_role_policies(RoleName=clean_name)
        for pol_name in inline.get("PolicyNames", []):
            client.delete_role_policy(RoleName=clean_name, PolicyName=pol_name)

        client.delete_role(RoleName=clean_name)
    except (ClientError, BotoCoreError) as exc:
        raise LzaError(f"Failed to delete IAM Role '{clean_name}': {exc}") from exc


def delete_policy(
    *,
    client: Any,
    policy_arn: str,
) -> None:
    """Detach from entities, delete non-default versions, and delete an IAM policy."""
    clean_arn = (policy_arn or "").strip()
    if not clean_arn:
        raise LzaError("IAM Policy ARN must not be empty")

    try:
        # Detach entities
        entities = client.list_entities_for_policy(PolicyArn=clean_arn)
        for r in entities.get("PolicyRoles", []):
            client.detach_role_policy(RoleName=r["RoleName"], PolicyArn=clean_arn)
        for u in entities.get("PolicyUsers", []):
            client.detach_user_policy(UserName=u["UserName"], PolicyArn=clean_arn)
        for g in entities.get("PolicyGroups", []):
            client.detach_group_policy(GroupName=g["GroupName"], PolicyArn=clean_arn)

        # Delete non-default versions
        versions = client.list_policy_versions(PolicyArn=clean_arn)
        for v in versions.get("Versions", []):
            if not v.get("IsDefaultVersion"):
                client.delete_policy_version(PolicyArn=clean_arn, VersionId=v["VersionId"])

        client.delete_policy(PolicyArn=clean_arn)
    except (ClientError, BotoCoreError) as exc:
        raise LzaError(f"Failed to delete IAM Policy '{clean_arn}': {exc}") from exc


__all__ = [
    "delete_policy",
    "delete_role",
]
