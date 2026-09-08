"""Status API adapter for the Web interface."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from lza_workbench.workflows.installer_init import (
    InstallerForm,
    InstallerSettingsRequest,
    apply_installer_settings,
    get_installer_parameters_schema,
)
from lza_workbench.workflows.installer_plan import (
    InstallerPlanResult,
    plan_installer_workflow,
)
from lza_workbench.workflows.status_config import (
    CodeCommitConfigurationRepositoryStatus,
    CodeConnectionConfigurationRepositoryStatus,
    ConfigurationStatusResult,
    GitConfigurationRepositoryStatus,
    S3ConfigurationRepositoryStatus,
    get_config_status_workflow,
)
from lza_workbench.workflows.status_installer import (
    InstallerStatusResult,
    get_installer_status_workflow,
)
from lza_workbench.workflows.status_root import (
    PipelineSummary,
    RootStatusResult,
    get_root_status_workflow,
)


class InstallerSettingsPayload(BaseModel):
    values: dict[str, str]


def create_status_router(*, workspace_dir: Path) -> APIRouter:
    """Create status routes bound to one workspace directory."""
    router = APIRouter()

    @router.get("/api/status")
    def get_status() -> dict[str, Any]:
        return serialize_root_status(get_root_status_workflow(target_dir=workspace_dir))

    @router.get("/api/status/config")
    def get_config_status() -> dict[str, Any]:
        return serialize_configuration_status(get_config_status_workflow(target_dir=workspace_dir))

    @router.get("/api/status/installer")
    def get_installer_status() -> dict[str, Any]:
        status_res = get_installer_status_workflow(target_dir=workspace_dir)
        form_res = get_installer_parameters_schema(target_dir=workspace_dir, all_fields=True)
        return serialize_installer_status(status_res, form_res)

    @router.post("/api/installer/settings")
    def save_installer_settings(payload: InstallerSettingsPayload) -> dict[str, Any]:
        result = apply_installer_settings(
            InstallerSettingsRequest(target_dir=workspace_dir, values=payload.values)
        )
        return {
            "success": True,
            "message": "Installer settings saved successfully.",
            "resolvedParameters": result.resolved_parameters,
        }

    @router.post("/api/installer/plan")
    def get_installer_plan() -> dict[str, Any]:
        return serialize_installer_plan(
            plan_installer_workflow(target_dir=workspace_dir, dry_run=True)
        )

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


def serialize_configuration_status(result: ConfigurationStatusResult) -> dict[str, Any]:
    """Translate configuration status result into browser API contract."""
    ws = result.workspace
    lg = result.local_git
    repo = result.repository
    pipe = result.pipeline
    sync_obj = result.synchronization
    remote_sync = sync_obj.remote_sync

    workspace_data = {
        "directory": str(ws.workspace_dir),
        "customerName": ws.customer_name,
        "lzaVersion": ws.lza_version,
        "profile": ws.profile,
        "region": ws.region,
        "identity": ws.aws_identity,
        "error": ws.aws_error,
        "isLive": ws.aws_identity is not None,
        "configDir": str(ws.config_dir),
        "configDirExists": ws.config_dir_exists,
        "yamlFiles": list(ws.yaml_files),
        "yamlFilesCount": len(ws.yaml_files),
        "initializedAt": ws.initialized_at.isoformat() if ws.initialized_at else None,
        "templateName": ws.template_name,
        "templateSource": ws.template_source,
        "driftedFields": list(ws.drifted_fields),
    }

    local_git_data: dict[str, Any] = {
        "isGit": lg.working_tree is not None,
        "workingTree": None,
        "syncStatus": None,
    }
    if lg.working_tree:
        wt = lg.working_tree
        local_git_data["workingTree"] = {
            "branch": wt.branch,
            "commit": wt.commit,
            "commitSubject": wt.commit_subject,
            "hasUncommitted": wt.has_uncommitted,
            "uncommittedCount": wt.uncommitted_count,
            "remoteUrl": wt.remote_url,
            "filesCount": wt.files_count,
        }
    if lg.sync_status:
        ss = lg.sync_status
        local_git_data["syncStatus"] = {
            "status": ss.status,
            "ahead": ss.ahead,
            "behind": ss.behind,
            "summary": ss.summary,
        }

    repo_data: dict[str, Any] = {}
    if isinstance(repo, S3ConfigurationRepositoryStatus):
        repo_data = {
            "type": "s3",
            "bucket": repo.bucket,
            "objectKey": repo.object_key,
            "bucketExists": repo.bucket_exists,
            "bucketAccessible": repo.bucket_accessible,
            "bucketVersioning": repo.bucket_versioning,
            "bucketEncryption": repo.bucket_encryption,
            "objectExists": repo.object_exists,
            "objectEtag": repo.object_etag,
            "objectVersionId": repo.object_version_id,
            "objectLastModified": (
                repo.object_last_modified.isoformat() if repo.object_last_modified else None
            ),
            "objectSize": repo.object_size,
            "error": repo.error,
        }
    elif isinstance(repo, CodeCommitConfigurationRepositoryStatus):
        repo_data = {
            "type": "codecommit",
            "repositoryName": repo.repository_name,
            "branchName": repo.branch_name,
            "exists": repo.exists,
            "accessible": repo.accessible,
            "branchExists": repo.branch_exists,
            "error": repo.error,
        }
    elif isinstance(repo, CodeConnectionConfigurationRepositoryStatus):
        repo_data = {
            "type": "codeconnection",
            "connectionArn": repo.connection_arn,
            "owner": repo.owner,
            "repositoryName": repo.repository_name,
            "branchName": repo.branch_name,
            "status": repo.status,
            "provider": repo.provider,
            "ownerAccount": repo.owner_account,
            "error": repo.error,
        }
    elif isinstance(repo, GitConfigurationRepositoryStatus):
        repo_data = {
            "type": "git",
            "repositoryUrl": repo.repository_url,
            "repositoryName": repo.repository_name,
            "branchName": repo.branch_name,
        }

    remote_sync_data = (
        {
            "status": remote_sync.status,
            "ahead": remote_sync.ahead,
            "behind": remote_sync.behind,
            "summary": remote_sync.summary,
            "isSynced": remote_sync.is_synced,
            "details": remote_sync.details,
        }
        if remote_sync
        else None
    )

    pipe_stages: list[dict[str, Any]] = []
    if pipe.state and pipe.state.stage_states:
        for stage in pipe.state.stage_states:
            actions = [
                {
                    "name": a.action_name,
                    "status": a.status,
                    "summary": a.summary,
                    "errorMessage": a.error_message,
                    "externalExecutionUrl": a.external_execution_url,
                }
                for a in stage.actions
            ]
            pipe_stages.append(
                {
                    "name": stage.stage_name,
                    "status": stage.status,
                    "actions": actions,
                }
            )

    pipeline_data = {
        "name": pipe.name,
        "arn": pipe.arn,
        "status": pipe.status,
        "executionId": pipe.execution_id,
        "failedStage": pipe.failed_stage,
        "failedAction": pipe.failed_action,
        "failedBuildUrl": pipe.failed_build_url,
        "error": pipe.error,
        "stages": pipe_stages,
    }

    synchronization_data = {
        "hasState": sync_obj.has_state,
        "recordedPipelineExecutionId": sync_obj.recorded_pipeline_execution_id,
        "uploadedAt": (sync_obj.uploaded_at.isoformat() if sync_obj.uploaded_at else None),
        "downloadedAt": (sync_obj.downloaded_at.isoformat() if sync_obj.downloaded_at else None),
        "artifactEtag": sync_obj.artifact_etag,
        "artifactVersionId": sync_obj.artifact_version_id,
    }

    return {
        "workspace": workspace_data,
        "localGit": local_git_data,
        "repository": repo_data,
        "remoteSync": remote_sync_data,
        "pipeline": pipeline_data,
        "synchronization": synchronization_data,
        "warnings": list(result.warnings),
    }


def serialize_installer_status(
    result: InstallerStatusResult, form: InstallerForm
) -> dict[str, Any]:
    """Translate installer status and schema into browser API contract."""
    cfg = result.config
    cfn = result.cfn_status
    pipe = result.pipeline_state
    align = result.state_alignment

    canonical = {
        "stackName": cfg.installer.stack_name or "AWSAccelerator-InstallerStack",
        "lzaVersion": cfg.lza.version,
        "acceleratorPrefix": cfg.lza.accelerator_prefix,
        "repositorySource": cfg.installer.source_code.repository_type,
        "repositoryName": cfg.installer.source_code.repository_name,
        "repositoryBranch": cfg.installer.source_code.branch,
        "repositoryOwner": cfg.installer.source_code.owner,
        "managementAccountEmail": cfg.installer.options.management_account_email,
        "logArchiveAccountEmail": cfg.installer.options.log_archive_account_email,
        "auditAccountEmail": cfg.installer.options.audit_account_email,
        "controlTowerEnabled": cfg.installer.options.control_tower_enabled,
        "enableApprovalStage": cfg.installer.options.enable_approval_stage,
        "approvalStageNotifyEmailList": cfg.installer.options.approval_stage_notify_email_list,
    }

    deployed = {
        "stackName": cfn.stack_name,
        "exists": cfn.exists,
        "stackStatus": cfn.stack_status,
        "stackId": cfn.stack_id,
        "deployedVersion": result.deployed_version,
        "creationTime": cfn.creation_time,
        "lastUpdatedTime": cfn.last_updated_time,
        "deployedParameters": dict(cfn.deployed_parameters),
        "outputs": dict(cfn.outputs),
        "error": cfn.error,
    }

    alignment_data = {
        "status": "In Sync" if (align and align.in_sync) else "Out of Sync" if align else "UNKNOWN",
        "inSync": align.in_sync if align else None,
        "configurationDrift": {
            k: {"deployed": v[0], "target": v[1]} for k, v in result.configuration_drift.items()
        },
    }

    current_stage = None
    current_action = None
    failed_stage = None
    failed_action = None
    failure_summary = None

    if pipe and pipe.stage_states:
        for stage in pipe.stage_states:
            for action in stage.actions:
                if action.status == "InProgress":
                    current_stage = stage.stage_name
                    current_action = action.action_name
                elif action.status == "Failed":
                    failed_stage = stage.stage_name
                    failed_action = action.action_name
                    failure_summary = action.error_message or action.summary

    pipeline_data = {
        "name": result.installer_pipeline_name,
        "exists": pipe.exists if pipe else False,
        "status": pipe.status if pipe else "NOT_CHECKED",
        "currentStage": current_stage,
        "currentAction": current_action,
        "failedStage": failed_stage,
        "failedAction": failed_action,
        "failureSummary": failure_summary,
        "isLive": (pipe.error is None) if pipe else False,
        "latestExecutionId": pipe.latest_execution_id if pipe else None,
    }

    form_fields = [
        {
            "name": f.name,
            "label": f.label,
            "default": f.default,
            "required": f.required,
            "allowedValues": list(f.allowed_values),
            "allowedPattern": f.allowed_pattern,
            "description": f.description,
        }
        for f in form.fields
    ]

    form_data = {
        "fields": form_fields,
        "resolvedParameters": dict(form.resolved_parameters),
    }

    aws_data = {
        "profile": result.profile,
        "region": result.region,
        "identity": result.aws_identity,
        "error": result.aws_error,
        "isLive": result.aws_identity is not None,
    }

    return {
        "workspace": {
            "directory": str(result.workspace_dir),
            "customerName": cfg.customer.name,
            "lzaVersion": cfg.lza.version,
        },
        "canonicalSettings": canonical,
        "deployed": deployed,
        "alignment": alignment_data,
        "pipeline": pipeline_data,
        "form": form_data,
        "aws": aws_data,
    }


def serialize_installer_plan(plan: InstallerPlanResult) -> dict[str, Any]:
    """Translate installer deployment plan into browser API contract."""
    cfn = plan.cloudformation_plan
    cc = plan.codecommit_plan

    return {
        "cloudformation": {
            "stackName": cfn.stack_name,
            "operation": cfn.operation,
            "stackStatus": cfn.stack_status,
            "parameterDiffs": {
                k: {"deployed": v[0], "target": v[1]} for k, v in cfn.parameter_diffs.items()
            },
            "resolvedParameters": dict(cfn.resolved_parameters),
        },
        "codecommit": {
            "repositoryName": cc.repository_name,
            "branchName": cc.branch_name,
            "status": cc.status,
            "creationRequired": cc.creation_required,
            "syncRequired": cc.sync_required,
            "officialRepoUrl": cc.official_repo_url,
            "officialVersionRef": cc.official_version_ref,
            "actions": list(cc.actions),
        },
        "githubSecretWarning": plan.github_secret_warning,
        "aws": {
            "profile": plan.profile,
            "region": plan.region,
            "identity": plan.aws_identity,
            "error": plan.aws_error,
            "isLive": plan.aws_identity is not None,
        },
    }
