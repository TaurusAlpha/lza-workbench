"""Status API adapter for the Web interface."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter

from lza_workbench.workflows.status_root import (
    PipelineSummary,
    RootStatusResult,
    get_root_status_workflow,
)


def create_status_router(*, workspace_dir: Path) -> APIRouter:
    """Create the status route bound to one workspace directory."""
    router = APIRouter()

    @router.get("/api/status")
    def get_status() -> dict[str, Any]:
        return serialize_root_status(get_root_status_workflow(target_dir=workspace_dir))

    return router


def serialize_root_status(result: RootStatusResult) -> dict[str, Any]:
    """Translate the root-status workflow result into the browser API contract."""
    sync = result.configuration_repo.git_sync_status
    rsync = result.configuration_repo.remote_sync
    return {
        "workspace": {
            "directory": str(result.workspace_dir),
            "customerName": result.customer_name,
            "lzaVersion": result.lza_version,
        },
        "aws": {
            "profile": result.profile,
            "region": result.region,
            "identity": result.aws_identity,
            "error": result.aws_error,
            "isLive": result.aws_identity is not None,
        },
        "installer": {
            "name": result.installer.name,
            "status": result.installer.status,
            "exists": result.installer.exists,
            "deployedVersion": result.installer.deployed_version,
            "isLive": result.installer.is_live,
        },
        "installerPipeline": _serialize_pipeline(result.installer_pipeline),
        "configuration": {
            "repositoryType": result.configuration_repo.repository_type,
            "target": result.configuration_repo.target,
            "localGitBranch": result.configuration_repo.local_git_branch,
            "localGitClean": result.configuration_repo.local_git_clean,
            "localGitUncommitted": result.configuration_repo.local_git_uncommitted,
            "gitSync": (
                {
                    "status": sync.status,
                    "ahead": sync.ahead,
                    "behind": sync.behind,
                    "summary": sync.summary,
                }
                if sync
                else None
            ),
            "remoteSync": (
                {
                    "status": rsync.status,
                    "ahead": rsync.ahead,
                    "behind": rsync.behind,
                    "summary": rsync.summary,
                    "isSynced": rsync.is_synced,
                }
                if rsync
                else None
            ),
            "isLive": result.configuration_repo.is_live,
        },

        "configurationPipeline": _serialize_pipeline(result.configuration_pipeline),
        "health": {
            "installer": result.health.installer,
            "configuration": result.health.configuration,
            "workspace": result.health.workspace,
            "isLive": result.health.is_live,
        },
    }


def _serialize_pipeline(pipeline: PipelineSummary) -> dict[str, Any]:
    return {
        "name": pipeline.name,
        "exists": pipeline.exists,
        "status": pipeline.status,
        "executionId": pipeline.execution_id,
        "startTime": pipeline.start_time,
        "durationSeconds": pipeline.duration_seconds,
        "currentStage": pipeline.current_stage,
        "currentAction": pipeline.current_action,
        "failedStage": pipeline.failed_stage,
        "failedAction": pipeline.failed_action,
        "failureSummary": pipeline.failure_summary,
        "isLive": pipeline.is_live,
    }
