"""Retained resource state management and selective deletion."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lza_workbench.infrastructure.aws.dynamodb import delete_table
from lza_workbench.infrastructure.aws.ecr import delete_repository
from lza_workbench.infrastructure.aws.iam import delete_policy, delete_role
from lza_workbench.infrastructure.aws.kms import delete_alias, schedule_key_deletion
from lza_workbench.infrastructure.aws.logs import delete_log_group
from lza_workbench.infrastructure.aws.s3 import empty_and_delete_s3_bucket
from lza_workbench.infrastructure.aws.session import AwsExecutionContext
from lza_workbench.workspace.persistence import (
    atomic_write_text,
    load_workspace_state,
    state_file_lock,
    update_workspace_state,
)
from lza_workbench.workspace.schema import WorkspaceState
from lza_workbench.workspace.uninstall.models import UninstallAccountTarget, UninstallTarget
from lza_workbench.workspace.uninstall.state import (
    RetainedResourceRecord,
    UninstallState,
)

RETAINED_RESOURCES_FILE = "retained-resources.json"


def _retained_record_key(record: RetainedResourceRecord) -> tuple[str, str, str, str]:
    return (
        record.account_id,
        record.region,
        record.resource_type,
        record.physical_id,
    )


def merge_retained_resource_records(
    existing: list[RetainedResourceRecord],
    incoming: list[RetainedResourceRecord],
) -> list[RetainedResourceRecord]:
    """Merge existing and newly discovered retained resource records.

    Preserves previously recorded resources whose stacks have already been deleted
    as well as prior deletion outcomes when restarting an interrupted uninstallation.
    """
    merged: dict[tuple[str, str, str, str], RetainedResourceRecord] = {
        _retained_record_key(rec): rec.model_copy(deep=True) for rec in existing
    }
    for rec in incoming:
        key = _retained_record_key(rec)
        prev = merged.get(key)
        if prev is None or rec.status != "retained":
            merged[key] = rec.model_copy(deep=True)
    return list(merged.values())


def read_retained_resources_from_state(
    target_or_workspace_dir: Path | UninstallTarget,
) -> list[RetainedResourceRecord]:
    """Read the list of retained resources stored in workspace state or record_dir."""
    if isinstance(target_or_workspace_dir, UninstallTarget):
        if target_or_workspace_dir.workspace_dir is not None:
            workspace_dir = target_or_workspace_dir.workspace_dir
        else:
            record_dir = target_or_workspace_dir.require_record_dir()
            retained_file = record_dir / RETAINED_RESOURCES_FILE
            if not retained_file.is_file():
                return []
            runtime_state = UninstallState.model_validate_json(
                retained_file.read_text(encoding="utf-8")
            )
            return list(runtime_state.retained_resources)
    else:
        workspace_dir = target_or_workspace_dir

    state = load_workspace_state(workspace_dir)
    uninstall_state = getattr(state, "uninstall", None)
    if uninstall_state and isinstance(uninstall_state, UninstallState):
        return list(uninstall_state.retained_resources)
    return []


def write_retained_resources_to_state(
    target_or_workspace_dir: Path | UninstallTarget,
    retained_resources: list[RetainedResourceRecord],
    *,
    status: str | None = None,
) -> list[RetainedResourceRecord]:
    """Record or update retained resources in workspace state or record_dir."""
    if isinstance(target_or_workspace_dir, UninstallTarget):
        if target_or_workspace_dir.workspace_dir is not None:
            workspace_dir = target_or_workspace_dir.workspace_dir
        else:
            record_dir = target_or_workspace_dir.require_record_dir()
            retained_file = record_dir / RETAINED_RESOURCES_FILE
            with state_file_lock(retained_file):
                current_uninstall = (
                    UninstallState.model_validate_json(retained_file.read_text(encoding="utf-8"))
                    if retained_file.is_file()
                    else UninstallState()
                )
                merged_records = merge_retained_resource_records(
                    list(current_uninstall.retained_resources),
                    retained_resources,
                )
                updated_uninstall = current_uninstall.model_copy(
                    update={
                        "retained_resources": merged_records,
                        "status": status or current_uninstall.status or "in_progress",
                        "uninstalled_at": current_uninstall.uninstalled_at or datetime.now(UTC),
                    }
                )
                atomic_write_text(
                    retained_file,
                    updated_uninstall.model_dump_json(indent=2) + "\n",
                )
            return merged_records
    else:
        workspace_dir = target_or_workspace_dir

    merged_result: list[RetainedResourceRecord] = []

    def _apply(state: WorkspaceState) -> None:
        nonlocal merged_result
        current_uninstall = getattr(state, "uninstall", None) or UninstallState()
        merged_result = merge_retained_resource_records(
            list(current_uninstall.retained_resources),
            retained_resources,
        )
        state.uninstall = current_uninstall.model_copy(
            update={
                "retained_resources": merged_result,
                "status": status or current_uninstall.status or "in_progress",
                "uninstalled_at": current_uninstall.uninstalled_at or datetime.now(UTC),
            }
        )

    update_workspace_state(workspace_dir, _apply)
    return merged_result


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
        if not empty_and_delete_s3_bucket(client=factory.get_client("s3"), bucket_name=phys_id):
            raise RuntimeError(f"Failed to empty and delete S3 bucket '{phys_id}'")
    else:
        raise NotImplementedError(f"Automated deletion not supported for type {res_type}")


def delete_selected_retained_resources(
    *,
    target: UninstallTarget,
    execution_context: AwsExecutionContext,
    retained_resources: list[RetainedResourceRecord] | None = None,
    selected_physical_ids: list[str] | None = None,
    account_targets: dict[str, UninstallAccountTarget] | list[UninstallAccountTarget] | None = None,
    assume_role_name: str = "AWSAccelerator-PipelineRole",
    on_event: Callable[[str, str], None] | None = None,
) -> list[RetainedResourceRecord]:
    """Loop over selected retained resources, delete them via AWS adapters, and update state."""
    records = (
        list(retained_resources)
        if retained_resources is not None
        else read_retained_resources_from_state(target)
    )
    if not records:
        return []

    mgmt_account_id = (
        target.management_account_id
        or execution_context.account_id
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

    write_retained_resources_to_state(target, records)
    return records


__all__ = [
    "delete_selected_retained_resources",
    "merge_retained_resource_records",
    "read_retained_resources_from_state",
    "write_retained_resources_to_state",
]
