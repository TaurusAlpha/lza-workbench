"""Status API adapter for the Web interface."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from lza_workbench.errors import LzaError
from lza_workbench.workflows.config_deploy import deploy_configuration_workflow
from lza_workbench.workflows.config_pull import (
    ConfigPullPreparation,
    ConfigPullRequest,
    ConfigPullResult,
    apply_config_pull,
    prepare_config_pull,
)
from lza_workbench.workflows.config_push import (
    ConfigPushPreparation,
    ConfigPushRequest,
    ConfigPushResult,
    apply_config_push,
    prepare_config_push,
)
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
from lza_workbench.workflows.pipeline_snapshot import (
    PipelineActionFailure,
    PipelineSnapshotResult,
    get_pipeline_diagnostics_workflow,
    get_pipeline_snapshot_workflow,
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
from lza_workbench.workflows.workspace_bootstrap import (
    BootstrapPlanResult,
    WorkspaceBootstrapResult,
    bootstrap_workspace_workflow,
    plan_bootstrap_workflow,
)
from lza_workbench.workflows.workspace_import import (
    ImportWorkspaceDiscovery,
    ImportWorkspacePreparation,
    ImportWorkspaceRequest,
    WorkspaceImportResult,
    apply_workspace_import,
    discover_import_workspace,
    prepare_workspace_import,
)
from lza_workbench.workflows.workspace_init import (
    WorkspaceInitResult,
    init_workspace_workflow,
)


class ActiveWorkspaceContext:
    """Manages active workspace directory and in-flight operations for the web server."""

    def __init__(self, workspace_dir: Path | None = None) -> None:
        self.workspace_dir: Path | None = workspace_dir.resolve() if workspace_dir else None
        self.prepared_import: ImportWorkspacePreparation | None = None

    def set_workspace_dir(self, workspace_dir: Path) -> None:
        self.workspace_dir = workspace_dir.resolve()
        self.prepared_import = None


class WorkspaceOpenPayload(BaseModel):
    directory: str


class WorkspaceInitPayload(BaseModel):
    customer_name: str
    workspace_dir: str | None = None
    aws_auth_type: str = "profile"
    aws_profile: str | None = None
    aws_region: str = "us-east-1"
    lza_version: str = "v1.15.5"
    force: bool = False
    skip_aws_check: bool = True


class WorkspaceImportDiscoverPayload(BaseModel):
    workspace_dir: str
    config_dir: str | None = None
    force: bool = False
    repair: bool = False


class WorkspaceImportPreparePayload(BaseModel):
    workspace_dir: str
    config_dir: str | None = None
    customer_name: str | None = None
    aws_auth_type: str = "profile"
    aws_profile: str | None = None
    aws_region: str = "us-east-1"
    lza_version: str = "v1.15.5"
    installer_stack_name: str | None = None
    force: bool = False
    repair: bool = False
    skip_aws_check: bool = False
    prime_credentials: bool = False


class InstallerSettingsPayload(BaseModel):
    values: dict[str, str]


class ConfigActionApplyPayload(BaseModel):
    overwrite_confirmed: bool = False
    force: bool = False


class BootstrapApplyPayload(BaseModel):
    github_token: str | None = None
    allow_missing_github_secret: bool = False


def create_status_router(
    *, workspace_dir: Path | ActiveWorkspaceContext | None = None
) -> APIRouter:
    """Create status and workspace routes bound to an active workspace context."""
    if isinstance(workspace_dir, ActiveWorkspaceContext):
        context = workspace_dir
    elif workspace_dir is not None:
        context = ActiveWorkspaceContext(workspace_dir)
    else:
        context = ActiveWorkspaceContext(None)

    router = APIRouter()

    def get_target_dir() -> Path:
        if context.workspace_dir is None:
            raise LzaError("No active workspace is open. Please open or create a workspace.")
        return context.workspace_dir

    @router.get("/api/workspace/active")
    def get_active_workspace() -> dict[str, Any]:
        if context.workspace_dir is None:
            return {"hasWorkspace": False, "workspaceDir": None}
        try:
            status_res = get_root_status_workflow(target_dir=context.workspace_dir)
            return {
                "hasWorkspace": True,
                "workspaceDir": str(status_res.workspace_dir),
                "customerName": status_res.customer_name,
                "lzaVersion": status_res.lza_version,
                "assessment": (
                    {
                        "metadataValid": status_res.assessment.metadata_valid,
                        "configurationPresent": status_res.assessment.configuration_present,
                        "installerConfigured": status_res.assessment.installer_configured,
                        "installerRecordedDeployed": (
                            status_res.assessment.installer_recorded_deployed
                        ),
                        "imported": status_res.assessment.imported,
                    }
                    if status_res.assessment
                    else None
                ),
            }
        except Exception:
            return {
                "hasWorkspace": False,
                "workspaceDir": str(context.workspace_dir),
            }

    @router.post("/api/workspace/open")
    def open_workspace(payload: WorkspaceOpenPayload) -> dict[str, Any]:
        target = Path(payload.directory).expanduser().resolve()
        if not target.is_dir():
            raise LzaError(f"Directory does not exist: {target}")
        status_res = get_root_status_workflow(target_dir=target)
        context.set_workspace_dir(target)
        return {
            "success": True,
            "workspaceDir": str(status_res.workspace_dir),
            "customerName": status_res.customer_name,
            "lzaVersion": status_res.lza_version,
        }

    @router.post("/api/workspace/init/preview")
    def preview_workspace_init(payload: WorkspaceInitPayload) -> dict[str, Any]:
        target_dir = Path(payload.workspace_dir).expanduser() if payload.workspace_dir else None
        result = init_workspace_workflow(
            customer_name=payload.customer_name,
            workspace_dir=target_dir,
            aws_auth_type=payload.aws_auth_type,
            aws_profile=payload.aws_profile,
            aws_region=payload.aws_region,
            lza_version=payload.lza_version,
            dry_run=True,
            force=payload.force,
            skip_aws_check=payload.skip_aws_check,
        )
        return serialize_workspace_init_result(result)

    @router.post("/api/workspace/init/apply")
    def apply_workspace_init_endpoint(payload: WorkspaceInitPayload) -> dict[str, Any]:
        target_dir = Path(payload.workspace_dir).expanduser() if payload.workspace_dir else None
        result = init_workspace_workflow(
            customer_name=payload.customer_name,
            workspace_dir=target_dir,
            aws_auth_type=payload.aws_auth_type,
            aws_profile=payload.aws_profile,
            aws_region=payload.aws_region,
            lza_version=payload.lza_version,
            dry_run=False,
            force=payload.force,
            skip_aws_check=payload.skip_aws_check,
        )
        context.set_workspace_dir(result.workspace_dir)
        return serialize_workspace_init_result(result)

    @router.post("/api/workspace/import/discover")
    def discover_workspace_import_endpoint(
        payload: WorkspaceImportDiscoverPayload,
    ) -> dict[str, Any]:
        ws_dir = Path(payload.workspace_dir).expanduser()
        cfg_dir = Path(payload.config_dir).expanduser() if payload.config_dir else None
        discovery = discover_import_workspace(
            workspace_dir=ws_dir,
            config_dir=cfg_dir,
            force=payload.force,
            repair=payload.repair,
        )
        return serialize_import_discovery(discovery)

    @router.post("/api/workspace/import/prepare")
    def prepare_workspace_import_endpoint(payload: WorkspaceImportPreparePayload) -> dict[str, Any]:
        ws_dir = Path(payload.workspace_dir).expanduser()
        cfg_dir = Path(payload.config_dir).expanduser() if payload.config_dir else None
        request = ImportWorkspaceRequest(
            workspace_dir=ws_dir,
            config_dir=cfg_dir,
            customer_name=payload.customer_name,
            aws_auth_type=payload.aws_auth_type,
            aws_profile=payload.aws_profile,
            aws_region=payload.aws_region,
            lza_version=payload.lza_version,
            installer_stack_name=payload.installer_stack_name,
            dry_run=False,
            force=payload.force,
            repair=payload.repair,
            skip_aws_check=payload.skip_aws_check,
            prime_credentials=payload.prime_credentials,
        )
        prep = prepare_workspace_import(request)
        context.prepared_import = prep
        return serialize_workspace_import_result(prep.result)

    @router.post("/api/workspace/import/apply")
    def apply_workspace_import_endpoint() -> dict[str, Any]:
        if context.prepared_import is None:
            raise LzaError("No prepared import found. Run prepare first before applying.")
        result = apply_workspace_import(context.prepared_import)
        context.set_workspace_dir(result.workspace_dir)
        return serialize_workspace_import_result(result)

    @router.get("/api/status")
    def get_status() -> dict[str, Any]:
        return serialize_root_status(get_root_status_workflow(target_dir=get_target_dir()))

    @router.get("/api/status/config")
    def get_config_status() -> dict[str, Any]:
        status_res = get_config_status_workflow(target_dir=get_target_dir())
        return serialize_configuration_status(status_res)

    @router.get("/api/status/installer")
    def get_installer_status() -> dict[str, Any]:
        target = get_target_dir()
        status_res = get_installer_status_workflow(target_dir=target)
        form_res = get_installer_parameters_schema(target_dir=target, all_fields=True)
        return serialize_installer_status(status_res, form_res)

    @router.post("/api/installer/settings")
    def save_installer_settings(payload: InstallerSettingsPayload) -> dict[str, Any]:
        result = apply_installer_settings(
            InstallerSettingsRequest(target_dir=get_target_dir(), values=payload.values)
        )
        return {
            "success": True,
            "message": "Installer settings saved successfully.",
            "resolvedParameters": result.resolved_parameters,
        }

    @router.post("/api/installer/plan")
    def get_installer_plan() -> dict[str, Any]:
        return serialize_installer_plan(
            plan_installer_workflow(target_dir=get_target_dir(), dry_run=True)
        )

    @router.post("/api/config/pull/prepare")
    def prepare_pull() -> dict[str, Any]:
        prep = prepare_config_pull(ConfigPullRequest(target_dir=get_target_dir()))
        return serialize_config_pull_preparation(prep)

    @router.post("/api/config/pull/apply")
    def apply_pull(payload: ConfigActionApplyPayload | None = None) -> dict[str, Any]:
        req = ConfigPullRequest(
            target_dir=get_target_dir(),
            overwrite_confirmed=payload.overwrite_confirmed if payload else False,
            force=payload.force if payload else False,
        )
        res = apply_config_pull(req)
        return serialize_config_pull_result(res)

    @router.post("/api/config/push/prepare")
    def prepare_push() -> dict[str, Any]:
        prep = prepare_config_push(ConfigPushRequest(target_dir=get_target_dir()))
        return serialize_config_push_preparation(prep)

    @router.post("/api/config/push/apply")
    def apply_push(payload: ConfigActionApplyPayload | None = None) -> dict[str, Any]:
        req = ConfigPushRequest(
            target_dir=get_target_dir(),
            overwrite_confirmed=payload.overwrite_confirmed if payload else False,
            force=payload.force if payload else False,
        )
        res = apply_config_push(req)
        return serialize_config_push_result(res)

    @router.get("/api/pipeline/snapshot")
    def pipeline_snapshot(
        type: str = "configuration",
        execution_id: str | None = None,
    ) -> dict[str, Any]:
        snapshot = get_pipeline_snapshot_workflow(
            target_dir=get_target_dir(),
            pipeline_type=type,
            execution_id=execution_id,
        )
        return serialize_pipeline_snapshot(snapshot)

    @router.get("/api/pipeline/diagnostics")
    def pipeline_diagnostics(
        type: str = "configuration",
        execution_id: str | None = None,
    ) -> list[dict[str, Any]]:
        failures = get_pipeline_diagnostics_workflow(
            target_dir=get_target_dir(),
            pipeline_type=type,
            execution_id=execution_id,
        )
        return serialize_pipeline_diagnostics(failures)

    @router.post("/api/config/deploy")
    def apply_deploy(payload: ConfigActionApplyPayload | None = None) -> dict[str, Any]:
        deploy_res = deploy_configuration_workflow(
            target_dir=get_target_dir(),
            dry_run=False,
            force=payload.force if payload else False,
            overwrite_confirmed=payload.overwrite_confirmed if payload else False,
            watch=False,
        )
        push_data = (
            serialize_config_push_result(deploy_res.push_result)
            if deploy_res.push_result
            else None
        )
        pipeline_started = deploy_res.start_result is not None
        execution_id = (
            deploy_res.start_result.execution_id if deploy_res.start_result else None
        )
        pipeline_name = (
            deploy_res.start_result.pipeline_name if deploy_res.start_result else None
        )
        message = (
            f"Configuration pushed and pipeline execution started ({execution_id})."
            if pipeline_started
            else "Configuration pushed successfully."
        )
        return {
            "success": True,
            "action": "deploy",
            "pushResult": push_data,
            "pipelineStarted": pipeline_started,
            "pipelineName": pipeline_name,
            "executionId": execution_id,
            "message": message,
        }

    @router.get("/api/bootstrap/plan")
    def get_bootstrap_plan() -> dict[str, Any]:
        return serialize_bootstrap_plan(
            plan_bootstrap_workflow(target_dir=get_target_dir(), dry_run=True)
        )

    @router.post("/api/bootstrap/apply")
    def apply_bootstrap(payload: BootstrapApplyPayload | None = None) -> dict[str, Any]:
        result = bootstrap_workspace_workflow(
            target_dir=get_target_dir(),
            dry_run=False,
            github_token=payload.github_token if payload else None,
            allow_missing_github_secret=payload.allow_missing_github_secret if payload else False,
        )
        return serialize_bootstrap_result(result)

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
        "assessment": (
            {
                "metadataValid": result.assessment.metadata_valid,
                "configurationPresent": result.assessment.configuration_present,
                "installerConfigured": result.assessment.installer_configured,
                "installerRecordedDeployed": result.assessment.installer_recorded_deployed,
                "imported": result.assessment.imported,
            }
            if result.assessment
            else None
        ),
        "capabilities": (
            [
                cap
                for cap, is_supported in [
                    ("metadata_valid", result.assessment.metadata_valid),
                    ("configuration_present", result.assessment.configuration_present),
                    ("installer_configured", result.assessment.installer_configured),
                    ("installer_recorded_deployed", result.assessment.installer_recorded_deployed),
                    ("imported", result.assessment.imported),
                ]
                if is_supported
            ]
            if result.assessment
            else []
        ),
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
    if pipe.state and pipe.state.stages:
        for stage in pipe.state.stages:
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

    if pipe and pipe.stages:
        for stage in pipe.stages:
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


def serialize_config_pull_preparation(prep: ConfigPullPreparation) -> dict[str, Any]:
    """Translate configuration pull preparation assessment into browser API contract."""
    res = prep.result
    target = (
        f"s3://{res.s3_bucket}/{res.s3_key}"
        if res.repository_type == "s3"
        else (res.git_remote_url or res.git_remote or "Remote Git")
    )
    if res.repository_type == "s3":
        operation = (
            f"Download and extract configuration archive from {target} "
            "into local configuration directory."
        )
    else:
        branch_desc = res.git_branch or "configured branch"
        operation = f"Pull remote changes from '{branch_desc}' into local repository."
    return {
        "action": "pull",
        "repositoryType": res.repository_type,
        "target": target,
        "branch": res.git_branch,
        "operation": operation,
        "requiresConfirmation": prep.confirmation_message is not None,
        "confirmationReason": prep.confirmation_message,
        "confirmationError": prep.confirmation_error,
        "trackedFiles": res.files_count,
    }


def serialize_config_pull_result(result: ConfigPullResult) -> dict[str, Any]:
    """Translate configuration pull execution result into browser API contract."""
    target = (
        f"s3://{result.s3_bucket}/{result.s3_key}"
        if result.repository_type == "s3"
        else (result.git_remote_url or "Remote Git")
    )
    message = (
        f"Successfully downloaded and extracted configuration from {target}."
        if result.repository_type == "s3" and result.extracted
        else f"Successfully pulled configuration from {target}."
    )
    diff = None
    if result.diff_result:
        diff = {
            "added": result.diff_result.added,
            "modified": result.diff_result.modified,
            "removed": result.diff_result.removed,
            "total": (
                len(result.diff_result.added)
                + len(result.diff_result.modified)
                + len(result.diff_result.removed)
            ),
        }
    return {
        "success": True,
        "action": "pull",
        "message": message,
        "repositoryType": result.repository_type,
        "target": target,
        "branch": result.git_branch,
        "commit": result.git_commit,
        "diff": diff,
        "stashedChanges": result.stashed_changes,
        "restoredChanges": result.restored_changes,
        "filesCount": result.files_count,
    }


def serialize_config_push_preparation(prep: ConfigPushPreparation) -> dict[str, Any]:
    """Translate configuration push preparation assessment into browser API contract."""
    res = prep.result
    target = (
        f"s3://{res.s3_bucket}/{res.s3_key}"
        if res.repository_type == "s3"
        else (res.git_remote_url or res.git_remote or "Remote Git")
    )
    operation = (
        f"Archive local configuration and upload to {target}."
        if res.repository_type == "s3"
        else f"Push local commits to branch '{res.git_branch or 'main'}' on remote repository."
    )
    return {
        "action": "push",
        "repositoryType": res.repository_type,
        "target": target,
        "branch": res.git_branch,
        "commit": res.git_commit,
        "operation": operation,
        "requiresConfirmation": prep.confirmation_message is not None,
        "confirmationReason": prep.confirmation_message,
        "trackedFiles": res.files_count,
    }


def serialize_config_push_result(result: ConfigPushResult) -> dict[str, Any]:
    """Translate configuration push execution result into browser API contract."""
    target = (
        f"s3://{result.s3_bucket}/{result.s3_key}"
        if result.repository_type == "s3"
        else (result.git_remote_url or "Remote Git")
    )
    message = (
        f"Successfully uploaded configuration archive to {target}."
        if result.repository_type == "s3"
        else f"Successfully pushed configuration to {target}."
    )
    diff = None
    if result.diff_result:
        diff = {
            "added": result.diff_result.added,
            "modified": result.diff_result.modified,
            "removed": result.diff_result.removed,
            "total": (
                len(result.diff_result.added)
                + len(result.diff_result.modified)
                + len(result.diff_result.removed)
            ),
        }
    return {
        "success": True,
        "action": "push",
        "message": message,
        "repositoryType": result.repository_type,
        "target": target,
        "branch": result.git_branch,
        "commit": result.git_commit,
        "diff": diff,
        "etag": result.etag,
        "versionId": result.version_id,
        "filesCount": result.files_count,
    }


def serialize_pipeline_snapshot(snapshot: PipelineSnapshotResult) -> dict[str, Any]:
    """Translate pipeline snapshot result into browser API contract."""
    stages_data: list[dict[str, Any]] = []
    for stage in snapshot.stages:
        actions_data: list[dict[str, Any]] = []
        for action in stage.actions:
            actions_data.append(
                {
                    "name": action.action_name,
                    "status": action.status,
                    "summary": action.summary,
                    "lastStatusChange": action.last_status_change,
                    "errorMessage": action.error_message,
                    "externalExecutionId": action.external_execution_id,
                    "externalExecutionUrl": action.external_execution_url,
                }
            )
        stages_data.append(
            {
                "name": stage.stage_name,
                "status": stage.status,
                "executionId": stage.execution_id,
                "actions": actions_data,
            }
        )

    return {
        "pipelineName": snapshot.pipeline_name,
        "pipelineType": snapshot.pipeline_type,
        "pipelineArn": snapshot.pipeline_arn,
        "executionId": snapshot.execution_id,
        "status": snapshot.status,
        "statusSummary": snapshot.status_summary,
        "isTerminal": snapshot.is_terminal,
        "isLive": snapshot.is_live,
        "startTime": snapshot.start_time,
        "lastUpdateTime": snapshot.last_update_time,
        "durationSeconds": snapshot.duration_seconds,
        "currentStage": snapshot.current_stage,
        "currentAction": snapshot.current_action,
        "failedStage": snapshot.failed_stage,
        "failedAction": snapshot.failed_action,
        "stages": stages_data,
        "error": snapshot.error,
    }


def serialize_pipeline_diagnostics(
    failures: list[PipelineActionFailure],
) -> list[dict[str, Any]]:
    """Translate pipeline action failures into structured root cause diagnostic objects."""
    results: list[dict[str, Any]] = []
    for failure in failures:
        root_cause_data = None
        if failure.root_cause:
            root_cause_data = {
                "category": failure.root_cause.category.value,
                "message": failure.root_cause.message,
                "resource": failure.root_cause.resource,
            }

        results.append(
            {
                "stageName": failure.stage_name,
                "actionName": failure.action_name,
                "failedResource": failure.failed_resource,
                "summary": failure.summary,
                "errorMessage": failure.error_message,
                "externalExecutionId": failure.external_execution_id,
                "externalExecutionUrl": failure.external_execution_url,
                "diagnosticDetails": failure.diagnostic_details,
                "rootCause": root_cause_data,
            }
        )
    return results


def serialize_bootstrap_plan(plan: BootstrapPlanResult) -> dict[str, Any]:
    """Translate bootstrap plan workflow result into the browser API contract."""
    is_mutation_required = (
        plan.bucket_planned_operation in {"CREATE", "UPDATE"}
        or plan.codecommit_repo_planned_operation == "CREATE"
        or plan.github_planned_operation == "CREATE"
    )
    is_blocked = (
        plan.codecommit_repo_planned_operation == "MISSING"
        or plan.github_planned_operation in {"MISSING", "INACCESSIBLE"}
    )
    return {
        "awsProfile": plan.aws_profile,
        "awsRegion": plan.aws_region,
        "accountId": plan.account_id,
        "plannedOperation": plan.planned_operation,
        "isMutationRequired": is_mutation_required and plan.is_live,
        "isBlocked": is_blocked,
        "imported": plan.imported,
        "isLive": plan.is_live,
        "error": plan.error,
        "resources": {
            "bucket": {
                "name": plan.bucket_name,
                "exists": plan.bucket_exists,
                "versioningEnabled": plan.versioning_enabled,
                "encryptionEnabled": plan.encryption_enabled,
                "plannedOperation": plan.bucket_planned_operation,
            },
            "codecommit": {
                "name": plan.codecommit_repo_name,
                "branch": plan.codecommit_branch_name,
                "exists": plan.codecommit_repo_exists,
                "branchExists": plan.codecommit_branch_exists,
                "plannedOperation": plan.codecommit_repo_planned_operation,
            }
            if plan.codecommit_repo_name
            else None,
            "github": {
                "secretName": plan.github_secret_name,
                "secretExists": plan.github_secret_exists,
                "secretAccessible": plan.github_secret_accessible,
                "repoOwner": plan.github_repo_owner,
                "repoName": plan.github_repo_name,
                "repoBranch": plan.github_repo_branch,
                "repoAccessible": plan.github_repo_accessible,
                "plannedOperation": plan.github_planned_operation,
            }
            if (plan.github_secret_name or plan.github_repo_name)
            else None,
        },
        "actions": [
            {
                "subject": a.subject,
                "operation": a.operation,
                "message": a.message,
                "severity": a.severity,
            }
            for a in plan.actions
        ],
        "warnings": plan.warnings,
    }


def serialize_bootstrap_result(result: WorkspaceBootstrapResult) -> dict[str, Any]:
    """Translate workspace bootstrap execution result into the browser API contract."""
    return {
        "success": True,
        "plannedOperation": result.planned_operation,
        "skipped": result.skipped,
        "actionsTaken": result.actions_taken,
        "warnings": result.warnings,
        "bucketName": result.bucket_name,
        "codecommitRepoName": result.codecommit_repo_name,
        "githubSecretName": result.github_secret_name,
        "githubSecretCreated": result.github_secret_created,
    }


def serialize_workspace_init_result(result: WorkspaceInitResult) -> dict[str, Any]:
    """Translate workspace init workflow result into the browser API contract."""
    return {
        "workspaceDir": str(result.workspace_dir),
        "customerSlug": result.config.customer.slug,
        "customerName": result.config.customer.name,
        "aws": {
            "profile": result.config.aws.profile,
            "region": result.config.aws.region,
        },
        "lzaVersion": result.config.lza.version,
        "plannedPaths": [str(p) for p in result.planned_paths],
        "existingDirectory": result.existing_directory,
        "identity": result.identity,
        "dryRun": result.dry_run,
    }


def serialize_workspace_import_result(result: WorkspaceImportResult) -> dict[str, Any]:
    """Translate workspace import workflow result into the browser API contract."""
    return {
        "workspaceDir": str(result.workspace_dir),
        "configDir": str(result.config_dir),
        "customerName": result.config.customer.name,
        "customerSlug": result.config.customer.slug,
        "aws": {
            "profile": result.config.aws.profile,
            "region": result.config.aws.region,
        },
        "lzaVersion": result.config.lza.version,
        "affectedPaths": [str(p) for p in result.affected_paths],
        "identity": result.identity,
        "alreadyImported": result.already_imported,
        "dryRun": result.dry_run,
        "repaired": result.repaired,
        "provenance": (
            {
                "repoType": result.provenance.repo_type,
                "repoName": result.provenance.repo_name,
                "remoteUrl": result.provenance.remote_url,
                "branch": result.provenance.branch,
                "commit": result.provenance.commit,
                "filesCount": result.provenance.files_count,
            }
            if result.provenance
            else None
        ),
        "validationSummary": result.validation_summary,
        "installerDiscovered": result.installer_discovered,
        "discoveredStackStatus": result.discovered_stack_status,
        "recommendations": result.recommendations,
    }


def serialize_import_discovery(discovery: ImportWorkspaceDiscovery) -> dict[str, Any]:
    """Translate import discovery into the browser API contract."""
    existing = discovery.existing
    existing_config = existing.config if existing else None
    return {
        "workspaceDir": str(discovery.workspace_dir),
        "configDir": str(discovery.config_dir),
        "hasExistingMetadata": existing is not None
        and (existing.config is not None or existing.state is not None),
        "existingCustomerName": existing_config.customer.name if existing_config else None,
        "existingAwsProfile": existing_config.aws.profile if existing_config else None,
        "existingAwsRegion": existing_config.aws.region if existing_config else None,
        "existingLzaVersion": existing_config.lza.version if existing_config else None,
        "isRepaired": existing.is_repaired if existing else False,
    }


