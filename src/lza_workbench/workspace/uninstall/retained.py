"""Retained resource state management and selective deletion."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from lza_workbench.infrastructure.aws.dynamodb import delete_table
from lza_workbench.infrastructure.aws.ecr import delete_repository
from lza_workbench.infrastructure.aws.iam import delete_policy, delete_role
from lza_workbench.infrastructure.aws.kms import delete_alias, schedule_key_deletion
from lza_workbench.infrastructure.aws.logs import delete_log_group
from lza_workbench.infrastructure.aws.s3 import empty_and_delete_s3_bucket
from lza_workbench.infrastructure.aws.session import AwsExecutionContext
from lza_workbench.workspace.persistence import load_workspace_state, write_workspace_state
from lza_workbench.workspace.uninstall.models import UninstallAccountTarget
from lza_workbench.workspace.uninstall.state import (
    RetainedResourceRecord,
    UninstallRuntimeState,
)

if TYPE_CHECKING:
    from lza_workbench.workspace.context import WorkspaceContext


def read_retained_resources_from_state(context: WorkspaceContext) -> list[RetainedResourceRecord]:
    """Read the list of retained resources currently stored in .lza/state.json."""
    state = load_workspace_state(context.workspace_dir)
    uninstall_state = getattr(state, "uninstall", None)
    if uninstall_state and isinstance(uninstall_state, UninstallRuntimeState):
        return list(uninstall_state.retained_resources)
    return []


def write_retained_resources_to_state(
    context: WorkspaceContext,
    retained_resources: list[RetainedResourceRecord],
    *,
    status: str | None = None,
) -> None:
    """Record or update retained resources in .lza/state.json."""
    state = load_workspace_state(context.workspace_dir)
    current_uninstall = getattr(state, "uninstall", None) or UninstallRuntimeState()

    updated_uninstall = current_uninstall.model_copy(
        update={
            "retained_resources": retained_resources,
            "status": status or current_uninstall.status or "in_progress",
            "uninstalled_at": current_uninstall.uninstalled_at or datetime.now(UTC),
        }
    )

    updated_state = state.model_copy(
        update={
            "uninstall": updated_uninstall,
            "updated_at": datetime.now(UTC),
        }
    )
    write_workspace_state(context.workspace_dir, updated_state)


def _get_factory_for_account_region(
    account_id: str,
    region: str,
    execution_context: AwsExecutionContext,
    mgmt_account_id: str,
    assume_role_name: str,
    account_targets: dict[str, UninstallAccountTarget] | None = None,
) -> Any:
    target = account_targets.get(account_id) if account_targets else None
    if target and target.profile:
        return execution_context.factory.for_profile(target.profile, region=region)
    if account_id == mgmt_account_id:
        return execution_context.factory.for_region(region)
    role_name = (target.role_name if target and target.role_name else None) or assume_role_name
    return execution_context.factory.for_account(
        account_id=account_id,
        role_name=role_name,
        region=region,
    )


def _dispatch_retained_deletion(factory: Any, res_type: str, phys_id: str) -> None:
    if res_type == "AWS::Logs::LogGroup":
        delete_log_group(client=factory.get_client("logs"), log_group_name=phys_id)
    elif res_type == "AWS::ECR::Repository":
        delete_repository(client=factory.get_client("ecr"), repository_name=phys_id, force=True)
    elif res_type == "AWS::DynamoDB::Table":
        delete_table(client=factory.get_client("dynamodb"), table_name=phys_id)
    elif res_type == "AWS::KMS::Key":
        schedule_key_deletion(client=factory.get_client("kms"), key_id=phys_id, pending_window_days=7)
    elif res_type == "AWS::KMS::Alias":
        delete_alias(client=factory.get_client("kms"), alias_name=phys_id)
    elif res_type == "AWS::IAM::Role":
        delete_role(client=factory.get_client("iam"), role_name=phys_id)
    elif res_type == "AWS::IAM::Policy":
        delete_policy(client=factory.get_client("iam"), policy_arn=phys_id)
    elif res_type in ("AWS::S3::Bucket", "S3::Bucket"):
        empty_and_delete_s3_bucket(client=factory.get_client("s3"), bucket_name=phys_id)
    else:
        raise NotImplementedError(f"Automated deletion not supported for type {res_type}")


def delete_selected_retained_resources(
    *,
    context: WorkspaceContext,
    execution_context: AwsExecutionContext,
    selected_physical_ids: list[str] | None = None,
    account_targets: dict[str, UninstallAccountTarget] | list[UninstallAccountTarget] | None = None,
    assume_role_name: str = "AWSAccelerator-PipelineRole",
    on_event: Callable[[str, str], None] | None = None,
) -> list[RetainedResourceRecord]:
    """Loop over selected retained resources in state, delete them via AWS adapters, and update state."""
    records = read_retained_resources_from_state(context)
    if not records:
        return []

    mgmt_account_id = (
        context.config.aws.account_id
        or (execution_context.identity.get("account") if execution_context.identity else "")
        or ""
    )
    targets_map: dict[str, UninstallAccountTarget] = {}
    if isinstance(account_targets, dict):
        targets_map = account_targets
    elif isinstance(account_targets, list):
        targets_map = {a.account_id: a for a in account_targets}

    selected_set = set(selected_physical_ids) if selected_physical_ids is not None else None

    for record in records:
        if selected_set is not None and record.physical_id not in selected_set:
            continue
        if record.status == "deleted":
            continue

        factory = _get_factory_for_account_region(
            record.account_id,
            record.region,
            execution_context,
            mgmt_account_id,
            assume_role_name,
            account_targets=targets_map,
        )

        res_type = record.resource_type
        phys_id = record.physical_id

        if on_event:
            on_event("delete_retained", f"Deleting retained {res_type} '{phys_id}'")

        try:
            _dispatch_retained_deletion(factory, res_type, phys_id)
            record.status = "deleted"
            record.error = None
            if on_event:
                on_event("retained_deleted", f"Deleted retained {res_type} '{phys_id}'")
        except NotImplementedError as exc:
            record.status = "unsupported"
            record.error = str(exc)
        except Exception as exc:
            record.status = "failed"
            record.error = str(exc)
            if on_event:
                on_event("retained_failed", f"Failed deleting retained {res_type} '{phys_id}': {exc}")

    write_retained_resources_to_state(context, records)
    return records


__all__ = [
    "delete_selected_retained_resources",
    "read_retained_resources_from_state",
    "write_retained_resources_to_state",
]
