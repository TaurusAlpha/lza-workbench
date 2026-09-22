"""Response serialization helpers for the Web interface."""

from __future__ import annotations

from typing import Any

from lza_workbench.configuration.pull import ConfigPullPreparation, ConfigPullResult
from lza_workbench.configuration.push import ConfigPushPreparation, ConfigPushResult
from lza_workbench.configuration.status import (
    CodeCommitConfigurationRepositoryStatus,
    CodeConnectionConfigurationRepositoryStatus,
    ConfigurationStatusResult,
    GitConfigurationRepositoryStatus,
    S3ConfigurationRepositoryStatus,
)
from lza_workbench.installer.initialize import InstallerForm
from lza_workbench.installer.plan import InstallerPlanResult
from lza_workbench.installer.status import InstallerStatusResult
from lza_workbench.pipeline.status import (
    PipelineActionFailure,
    PipelineSnapshotResult,
)
from lza_workbench.status.observer import PipelineSummary, RootStatusResult
from lza_workbench.workspace.import_workspace import (
    ImportWorkspaceDiscovery,
    WorkspaceImportResult,
)
from lza_workbench.workspace.initialize import WorkspaceInitResult


def serialize_root_status(result: RootStatusResult) -> dict[str, Any]:
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


def serialize_workspace_init_result(result: WorkspaceInitResult) -> dict[str, Any]:
    return {
        "workspaceDir": str(result.workspace_dir),
        "customerSlug": result.config.customer.slug,
        "customerName": result.config.customer.name,
        "aws": {
            "profile": result.config.aws.profile,
            "roleArn": result.config.aws.role_arn,
            "region": result.config.aws.region,
        },
        "lzaVersion": result.config.lza.version,
        "plannedPaths": [str(p) for p in result.planned_paths],
        "existingDirectory": result.existing_directory,
        "identity": result.identity,
        "dryRun": result.dry_run,
    }


def serialize_workspace_import_result(result: WorkspaceImportResult) -> dict[str, Any]:
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


__all__ = [
    "serialize_config_pull_preparation",
    "serialize_config_pull_result",
    "serialize_config_push_preparation",
    "serialize_config_push_result",
    "serialize_configuration_status",
    "serialize_import_discovery",
    "serialize_installer_plan",
    "serialize_installer_status",
    "serialize_pipeline_diagnostics",
    "serialize_pipeline_snapshot",
    "serialize_root_status",
    "serialize_workspace_import_result",
    "serialize_workspace_init_result",
]
