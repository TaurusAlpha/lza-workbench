"""Execution engine for LZA solution uninstallation."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lza_workbench.infrastructure.aws.cloudformation import (
    delete_cloudformation_stack,
    disable_stack_termination_protection,
)
from lza_workbench.infrastructure.aws.s3 import empty_and_delete_s3_bucket
from lza_workbench.infrastructure.aws.session import AwsExecutionContext
from lza_workbench.installer.runtime import InstallerRuntimeState
from lza_workbench.pipeline.runtime import PipelinesRuntimeState
from lza_workbench.workspace.persistence import load_workspace_state, write_workspace_state

if TYPE_CHECKING:
    from lza_workbench.workspace.context import WorkspaceContext
from lza_workbench.workspace.uninstall.models import (
    UninstallAccountTarget,
    UninstallOptions,
    UninstallPlan,
    UninstallProgress,
    UninstallStack,
)
from lza_workbench.workspace.uninstall.retained import (
    delete_selected_retained_resources,
    write_retained_resources_to_state,
)
from lza_workbench.workspace.uninstall.state import RetainedResourceRecord


def _get_progress_file_path(context: WorkspaceContext) -> Path:
    return context.state_dir / "uninstall-progress.json"


def load_or_init_progress(context: WorkspaceContext) -> UninstallProgress:
    """Load existing progress file if present, else initialize new."""
    progress_file = _get_progress_file_path(context)
    if progress_file.is_file():
        try:
            data = json.loads(progress_file.read_text(encoding="utf-8"))
            return UninstallProgress(
                customer_slug=data.get("customer_slug", context.config.customer.slug),
                started_at=data.get("started_at", datetime.now(UTC).isoformat()),
                completed_at=data.get("completed_at"),
                status=data.get("status", "IN_PROGRESS"),
                deleted_stacks=data.get("deleted_stacks", []),
                failed_stacks=data.get("failed_stacks", []),
                deleted_retained=data.get("deleted_retained", []),
                deleted_buckets=data.get("deleted_buckets", []),
                retained_resources_remaining=data.get("retained_resources_remaining", []),
                error=data.get("error"),
            )
        except Exception:
            pass

    return UninstallProgress(
        customer_slug=context.config.customer.slug,
        started_at=datetime.now(UTC).isoformat(),
    )


def save_progress(context: WorkspaceContext, progress: UninstallProgress) -> None:
    """Persist progress to .lza/uninstall-progress.json."""
    progress_file = _get_progress_file_path(context)
    progress_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "customer_slug": progress.customer_slug,
        "started_at": progress.started_at,
        "completed_at": progress.completed_at,
        "status": progress.status,
        "deleted_stacks": progress.deleted_stacks,
        "failed_stacks": progress.failed_stacks,
        "deleted_retained": progress.deleted_retained,
        "deleted_buckets": progress.deleted_buckets,
        "retained_resources_remaining": progress.retained_resources_remaining,
        "error": progress.error,
    }
    progress_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _get_factory_for_account(
    account: UninstallAccountTarget,
    region: str,
    execution_context: AwsExecutionContext,
    options: UninstallOptions,
) -> Any:
    if account.profile:
        return execution_context.factory.for_profile(account.profile, region=region)
    if account.is_management:
        return execution_context.factory.for_region(region)
    role_name = account.role_name or options.assume_role_name
    return execution_context.factory.for_account(
        account.account_id, role_name=role_name, region=region
    )


def _delete_single_stack(
    context: WorkspaceContext,
    execution_context: AwsExecutionContext,
    stack: UninstallStack,
    acc: UninstallAccountTarget,
    options: UninstallOptions,
    progress: UninstallProgress,
    on_event: Callable[[str, str], None] | None = None,
) -> None:
    factory = _get_factory_for_account(acc, stack.region, execution_context, options)
    try:
        cfn_client = factory.get_client("cloudformation")
        if stack.termination_protection:
            if on_event:
                on_event("protect", f"Disabling termination protection for {stack.stack_name}")
            disable_stack_termination_protection(client=cfn_client, stack_name=stack.stack_name)

        if on_event:
            on_event("delete_stack", f"Deleting stack {stack.stack_name} in {stack.region}")

        delete_cloudformation_stack(client=cfn_client, stack_name=stack.stack_name)
        progress.deleted_stacks.append(stack.stack_name)
        save_progress(context, progress)

        if on_event:
            on_event("stack_deleted", f"Successfully deleted stack {stack.stack_name}")
    except Exception as exc:
        err_msg = str(exc)
        if on_event:
            on_event("stack_failed", f"Failed deleting stack {stack.stack_name}: {err_msg}")
        progress.failed_stacks.append(
            {
                "stack_name": stack.stack_name,
                "account_id": stack.account_id,
                "region": stack.region,
                "error": err_msg,
            }
        )
        save_progress(context, progress)


def _delete_all_stacks(
    context: WorkspaceContext,
    execution_context: AwsExecutionContext,
    plan: UninstallPlan,
    options: UninstallOptions,
    account_map: dict[str, UninstallAccountTarget],
    progress: UninstallProgress,
    on_event: Callable[[str, str], None] | None = None,
) -> None:
    for stack in plan.stacks:
        if stack.stack_name in progress.deleted_stacks:
            if on_event:
                on_event("skip", f"Stack already deleted: {stack.stack_name}")
            continue

        acc = account_map.get(stack.account_id) or UninstallAccountTarget(
            account_id=stack.account_id,
            name=stack.account_name,
            is_management=(stack.account_id == context.config.aws.account_id),
            role_name=options.assume_role_name,
        )
        _delete_single_stack(context, execution_context, stack, acc, options, progress, on_event)


def _delete_all_s3_buckets(
    context: WorkspaceContext,
    execution_context: AwsExecutionContext,
    plan: UninstallPlan,
    options: UninstallOptions,
    account_map: dict[str, UninstallAccountTarget],
    progress: UninstallProgress,
    on_event: Callable[[str, str], None] | None = None,
) -> None:
    for b in plan.s3_buckets:
        if b.bucket_name in progress.deleted_buckets:
            continue

        acc = account_map.get(b.account_id) or UninstallAccountTarget(
            account_id=b.account_id,
            name=b.account_id,
            role_name=options.assume_role_name,
        )
        factory = _get_factory_for_account(acc, b.region, execution_context, options)

        try:
            s3_client = factory.get_client("s3")
            if on_event:
                on_event("delete_bucket", f"Emptying and deleting S3 bucket {b.bucket_name}")
            success = empty_and_delete_s3_bucket(client=s3_client, bucket_name=b.bucket_name)
            if success:
                b.actually_deleted = True
                b.action_status = "DELETED"
                progress.deleted_buckets.append(b.bucket_name)
                save_progress(context, progress)
        except Exception as exc:
            if on_event:
                on_event("bucket_failed", f"Failed deleting S3 bucket {b.bucket_name}: {exc}")


def _process_retained_resources(
    context: WorkspaceContext,
    execution_context: AwsExecutionContext,
    plan: UninstallPlan,
    options: UninstallOptions,
    progress: UninstallProgress,
    selected_retained_ids: list[str] | None = None,
    on_event: Callable[[str, str], None] | None = None,
) -> None:
    if options.delete_retained_resources:
        updated_records = delete_selected_retained_resources(
            context=context,
            execution_context=execution_context,
            selected_physical_ids=selected_retained_ids,
            account_targets=plan.accounts,
            assume_role_name=options.assume_role_name,
            on_event=on_event,
        )
        for rec in updated_records:
            entry = {
                "physical_id": rec.physical_id,
                "resource_type": rec.resource_type,
                "account_id": rec.account_id,
                "region": rec.region,
            }
            if rec.status == "deleted":
                progress.deleted_retained.append(entry)
            else:
                progress.retained_resources_remaining.append(entry)
        save_progress(context, progress)
    else:
        for r in plan.retained_resources:
            progress.retained_resources_remaining.append(
                {
                    "physical_id": r.physical_id,
                    "resource_type": r.resource_type,
                    "account_id": r.account_id,
                    "region": r.region,
                }
            )


def _cleanup_workspace_state(
    context: WorkspaceContext,
    progress: UninstallProgress,
) -> None:
    has_deleted_installer = any("Installer" in s for s in progress.deleted_stacks)
    has_deleted_pipeline = any("Pipeline" in s for s in progress.deleted_stacks)

    if not (has_deleted_installer or has_deleted_pipeline):
        return

    try:
        current_state = load_workspace_state(context.workspace_dir)
        installer_state = (
            InstallerRuntimeState() if has_deleted_installer else current_state.installer
        )
        pipeline_state = (
            PipelinesRuntimeState() if has_deleted_pipeline else current_state.pipelines
        )

        updated_state = current_state.model_copy(
            update={
                "installer": installer_state,
                "pipelines": pipeline_state,
                "updated_at": datetime.now(UTC),
            }
        )
        write_workspace_state(context.workspace_dir, updated_state)
    except Exception:
        pass


def execute_uninstall(
    *,
    context: WorkspaceContext,
    execution_context: AwsExecutionContext,
    plan: UninstallPlan,
    options: UninstallOptions,
    selected_retained_ids: list[str] | None = None,
    on_event: Callable[[str, str], None] | None = None,
) -> UninstallProgress:
    """Execute the uninstallation plan step-by-step."""
    progress = load_or_init_progress(context)

    # 1. Record all retained resources from CF templates into .lza/state.json
    retained_records = [
        RetainedResourceRecord(
            account_id=r.account_id,
            region=r.region,
            stack_name=r.stack_name,
            logical_id=r.logical_id,
            physical_id=r.physical_id,
            resource_type=r.resource_type,
            status="retained",
        )
        for r in plan.retained_resources
    ]
    write_retained_resources_to_state(context, retained_records, status="in_progress")

    if options.dry_run:
        progress.status = "PREVIEW_DRY_RUN"
        return progress

    account_map = {acc.account_id: acc for acc in plan.accounts}

    # 2. Stacks deletion
    _delete_all_stacks(context, execution_context, plan, options, account_map, progress, on_event)

    # 3. S3 Buckets deletion
    if options.delete_s3_buckets:
        _delete_all_s3_buckets(
            context, execution_context, plan, options, account_map, progress, on_event
        )

    # 4. Retained resources deletion or recording
    _process_retained_resources(
        context,
        execution_context,
        plan,
        options,
        progress,
        selected_retained_ids=selected_retained_ids,
        on_event=on_event,
    )

    # 5. Workspace state metadata cleanup
    _cleanup_workspace_state(context, progress)

    # 6. Finalize status
    progress.completed_at = datetime.now(UTC).isoformat()
    progress.status = "FAILED" if progress.failed_stacks else "COMPLETED"
    save_progress(context, progress)

    return progress


__all__ = [
    "execute_uninstall",
    "load_or_init_progress",
    "save_progress",
]
