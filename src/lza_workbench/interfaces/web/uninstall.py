"""Web API router for LZA uninstallation operations."""

from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from lza_workbench.errors import LzaError
from lza_workbench.infrastructure.aws.session import resolve_aws_execution_context
from lza_workbench.interfaces.web.context import ActiveWorkspaceContext
from lza_workbench.workspace.context import WorkspaceCapability, load_workspace_context
from lza_workbench.workspace.uninstall.executor import (
    execute_uninstall,
    load_or_init_progress,
)
from lza_workbench.workspace.uninstall.inventory import build_uninstall_plan
from lza_workbench.workspace.uninstall.models import (
    UninstallOptions,
    UninstallPlan,
)
from lza_workbench.workspace.uninstall.retained import read_retained_resources_from_state


class UninstallPlanRequest(BaseModel):
    """Payload to request an uninstallation plan preview."""

    regions: list[str] = Field(default_factory=list)
    all_regions: bool = False
    accounts: list[str] = Field(default_factory=list)
    assume_role_name: str = "AWSAccelerator-PipelineRole"
    profiles_file: str | None = None
    skip_installer: bool = False
    skip_pipeline: bool = False


class UninstallApplyRequest(BaseModel):
    """Payload to apply uninstallation."""

    customer_slug_confirmation: str
    regions: list[str] = Field(default_factory=list)
    all_regions: bool = False
    accounts: list[str] = Field(default_factory=list)
    assume_role_name: str = "AWSAccelerator-PipelineRole"
    profiles_file: str | None = None
    delete_s3_buckets: bool = False
    selected_bucket_names: list[str] | None = None
    delete_retained_resources: bool = False
    selected_retained_ids: list[str] | None = None
    skip_installer: bool = False
    skip_pipeline: bool = False


def _serialize_plan(plan: UninstallPlan) -> dict[str, Any]:
    return {
        "customerName": plan.customer_name,
        "customerSlug": plan.customer_slug,
        "acceleratorPrefix": plan.accelerator_prefix,
        "accounts": [
            {
                "accountId": acc.account_id,
                "name": acc.name,
                "isManagement": acc.is_management,
                "profile": acc.profile,
                "roleName": acc.role_name,
            }
            for acc in plan.accounts
        ],
        "regions": plan.regions,
        "stacks": [
            {
                "stackName": s.stack_name,
                "accountId": s.account_id,
                "accountName": s.account_name,
                "region": s.region,
                "creationTime": s.creation_time.isoformat() if s.creation_time else None,
                "terminationProtection": s.termination_protection,
                "isPipelineOrInstaller": s.is_pipeline_or_installer,
                "retainedResources": [
                    {
                        "logicalId": r.logical_id,
                        "physicalId": r.physical_id,
                        "resourceType": r.resource_type,
                    }
                    for r in s.retained_resources
                ],
            }
            for s in plan.stacks
        ],
        "s3Buckets": [
            {
                "bucketName": b.bucket_name,
                "accountId": b.account_id,
                "region": b.region,
                "actionStatus": b.action_status,
            }
            for b in plan.s3_buckets
        ],
        "retainedResources": [
            {
                "accountId": r.account_id,
                "region": r.region,
                "stackName": r.stack_name,
                "logicalId": r.logical_id,
                "physicalId": r.physical_id,
                "resourceType": r.resource_type,
                "actionStatus": r.action_status,
            }
            for r in plan.retained_resources
        ],
        "totalStacks": plan.total_stacks,
        "protectedStacks": plan.protected_stacks,
        "totalS3Buckets": plan.total_s3_buckets,
        "totalRetainedResources": plan.total_retained_resources,
    }


# Track active uninstall thread to prevent concurrent runs
_active_uninstall_lock = threading.Lock()
_is_uninstall_running = False


def create_uninstall_router(workspace_dir: ActiveWorkspaceContext) -> APIRouter:
    router = APIRouter(tags=["uninstall"])

    @router.post("/api/uninstall/plan")
    def get_uninstall_plan_endpoint(payload: UninstallPlanRequest) -> dict[str, Any]:
        target_dir = workspace_dir.require_workspace_dir()
        context = load_workspace_context(
            target_dir=target_dir,
            required_capabilities=(WorkspaceCapability.METADATA_VALID,),
        )

        execution_context = resolve_aws_execution_context(
            profile=context.config.aws.profile,
            region=context.config.aws.region,
            role_arn=context.config.aws.role_arn,
            expected_account_id=context.config.aws.account_id,
            prime_credentials=context.config.aws.prime_credentials,
            validate_identity=True,
            require_identity=True,
        )

        options = UninstallOptions(
            dry_run=True,
            regions=payload.regions,
            all_regions=payload.all_regions,
            accounts=payload.accounts,
            assume_role_name=payload.assume_role_name,
            profiles_file=payload.profiles_file,
            skip_installer=payload.skip_installer,
            skip_pipeline=payload.skip_pipeline,
        )

        plan = build_uninstall_plan(
            context=context,
            execution_context=execution_context,
            options=options,
        )

        return {
            "success": True,
            "plan": _serialize_plan(plan),
        }

    @router.post("/api/uninstall/apply")
    def apply_uninstall_endpoint(payload: UninstallApplyRequest) -> dict[str, Any]:
        global _is_uninstall_running

        target_dir = workspace_dir.require_workspace_dir()
        context = load_workspace_context(
            target_dir=target_dir,
            required_capabilities=(WorkspaceCapability.METADATA_VALID,),
        )

        # 1. Validate customer slug confirmation
        expected_slug = context.config.customer.slug.strip()
        provided_slug = (payload.customer_slug_confirmation or "").strip()
        if provided_slug != expected_slug:
            raise LzaError(
                f"Confirmation slug mismatch: Expected '{expected_slug}', got '{provided_slug}'."
            )

        with _active_uninstall_lock:
            if _is_uninstall_running:
                raise LzaError("An uninstallation execution is already currently running.")
            _is_uninstall_running = True

        execution_context = resolve_aws_execution_context(
            profile=context.config.aws.profile,
            region=context.config.aws.region,
            role_arn=context.config.aws.role_arn,
            expected_account_id=context.config.aws.account_id,
            prime_credentials=context.config.aws.prime_credentials,
            validate_identity=True,
            require_identity=True,
        )

        options = UninstallOptions(
            dry_run=False,
            force=True,
            regions=payload.regions,
            all_regions=payload.all_regions,
            accounts=payload.accounts,
            assume_role_name=payload.assume_role_name,
            profiles_file=payload.profiles_file,
            delete_s3_buckets=payload.delete_s3_buckets,
            delete_retained_resources=payload.delete_retained_resources,
            skip_installer=payload.skip_installer,
            skip_pipeline=payload.skip_pipeline,
        )

        # Build plan
        plan = build_uninstall_plan(
            context=context,
            execution_context=execution_context,
            options=options,
        )

        # Filter S3 buckets if specific selection provided
        if payload.delete_s3_buckets and payload.selected_bucket_names is not None:
            selected_set = set(payload.selected_bucket_names)
            plan.s3_buckets = [b for b in plan.s3_buckets if b.bucket_name in selected_set]

        def _run_worker():
            global _is_uninstall_running
            try:
                execute_uninstall(
                    context=context,
                    execution_context=execution_context,
                    plan=plan,
                    options=options,
                    selected_retained_ids=payload.selected_retained_ids,
                )
            finally:
                with _active_uninstall_lock:
                    _is_uninstall_running = False

        thread = threading.Thread(target=_run_worker, daemon=True)
        thread.start()

        return {
            "success": True,
            "status": "IN_PROGRESS",
            "message": "Uninstallation started successfully in the background.",
        }

    @router.get("/api/uninstall/progress")
    def get_uninstall_progress_endpoint() -> dict[str, Any]:
        global _is_uninstall_running
        target_dir = workspace_dir.require_workspace_dir()
        context = load_workspace_context(
            target_dir=target_dir,
            required_capabilities=(WorkspaceCapability.METADATA_VALID,),
        )

        progress = load_or_init_progress(context)
        retained_records = read_retained_resources_from_state(context)

        return {
            "isRunning": _is_uninstall_running,
            "status": progress.status,
            "customerSlug": progress.customer_slug,
            "startedAt": progress.started_at,
            "completedAt": progress.completed_at,
            "deletedStacks": progress.deleted_stacks,
            "failedStacks": progress.failed_stacks,
            "deletedBuckets": progress.deleted_buckets,
            "deletedRetained": progress.deleted_retained,
            "retainedRemaining": progress.retained_resources_remaining,
            "retainedInState": [
                {
                    "accountId": r.account_id,
                    "region": r.region,
                    "stackName": r.stack_name,
                    "logicalId": r.logical_id,
                    "physicalId": r.physical_id,
                    "resourceType": r.resource_type,
                    "status": r.status,
                    "error": r.error,
                }
                for r in retained_records
            ],
            "error": progress.error,
        }

    return router


__all__ = ["create_uninstall_router"]
