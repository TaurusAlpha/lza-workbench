"""Workflow for gathering configuration repository status data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from lza_workbench.aws.codebuild import fetch_codebuild_diagnostics
from lza_workbench.aws.codecommit import inspect_codecommit_config_repository
from lza_workbench.aws.codeconnections import inspect_codeconnection
from lza_workbench.aws.codepipeline import PipelineStateResult, get_pipeline_state
from lza_workbench.aws.context import resolve_aws_execution_context
from lza_workbench.aws.s3 import inspect_s3_bucket, inspect_s3_object_safe
from lza_workbench.configuration.git import (
    GitRemoteSyncStatus,
    GitWorkingTreeStatus,
    get_git_remote_sync_status,
    get_git_working_tree_status,
)
from lza_workbench.configuration.rendering import capture_init_values_snapshot
from lza_workbench.configuration.schema import get_canonical_config_s3_bucket
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context
from lza_workbench.workspace.schema import WorkspaceConfig, WorkspaceState


@dataclass(frozen=True)
class ConfigurationStatusResult:
    """All data needed to render configuration-source status."""

    workspace_dir: Path
    customer_name: str
    lza_version: str
    profile: str
    region: str
    aws_identity: dict[str, str] | None
    aws_error: str | None
    config_dir: Path
    config_dir_exists: bool
    yaml_files: tuple[str, ...]
    repository_type: str
    repository_bucket: str | None
    repository_prefix: str
    repository_key: str
    repository_name: str | None
    repository_branch: str | None
    codeconnection_arn: str | None
    owner: str | None
    repository_url: str | None
    initialized_at: datetime | None
    template_name: str | None
    template_source: str | None
    drifted_fields: tuple[str, ...]
    git_working_tree: GitWorkingTreeStatus | None
    git_sync_status: GitRemoteSyncStatus | None
    s3_bucket_exists: bool | None
    s3_bucket_accessible: bool | None
    s3_bucket_versioning: bool | None
    s3_bucket_encryption: bool | None
    s3_object_exists: bool | None
    s3_object_etag: str | None
    s3_object_version_id: str | None
    s3_object_last_modified: datetime | None
    s3_object_size: int | None
    s3_error: str | None
    codecommit_exists: bool | None
    codecommit_accessible: bool | None
    codecommit_branch_exists: bool | None
    codecommit_error: str | None
    codeconnection_status: str | None
    codeconnection_provider: str | None
    codeconnection_owner_account: str | None
    codeconnection_error: str | None
    pipeline_name: str
    pipeline_arn: str
    pipeline_status: str | None
    pipeline_execution_id: str | None
    pipeline_failed_stage: str | None
    pipeline_failed_action: str | None
    pipeline_failed_build_url: str | None
    pipeline_error: str | None
    pipeline_state: PipelineStateResult | None

    uploaded_at: object | None
    downloaded_at: object | None
    artifact_etag: str | None
    artifact_version_id: str | None
    has_state: bool
    warnings: tuple[str, ...]


def _compile_warnings(
    *,
    config_dir_exists: bool,
    drifted_fields: tuple[str, ...],
    git_working_tree: GitWorkingTreeStatus | None,
    git_sync_status: GitRemoteSyncStatus | None,
    repository_type: str,
    s3_bucket_name: str | None = None,
    s3_bucket_exists: bool | None,
    s3_bucket_accessible: bool | None,
    s3_object_exists: bool | None,
    codecommit_exists: bool | None,
    codecommit_accessible: bool | None,
    codecommit_branch_exists: bool | None,
    codeconnection_status: str | None,
    pipeline_name: str,
    pipeline_status: str | None,
    pipeline_failed_stage: str | None,
    pipeline_failed_action: str | None,
) -> tuple[str, ...]:
    warnings: list[str] = []

    if not config_dir_exists:
        warnings.append(
            "Local configuration directory is missing. "
            "Run 'lza config init' or 'lza config pull' to initialize it."
        )

    if drifted_fields:
        fields_str = ", ".join(drifted_fields)
        warnings.append(
            f"Workspace settings changed since template initialization ({fields_str}). "
            "Run 'lza config init --force' to re-apply the template."
        )

    if git_working_tree and git_working_tree.has_uncommitted:
        warnings.append(
            f"Local configuration contains {git_working_tree.uncommitted_count} uncommitted "
            "change(s). Commit or stash your changes before pushing."
        )

    if git_sync_status:
        if git_sync_status.status == "Behind":
            warnings.append(
                f"Local configuration is behind remote repository by {git_sync_status.behind} "
                "commit(s). Run 'lza config pull' to synchronize."
            )
        elif git_sync_status.status == "Diverged":
            warnings.append(
                f"Local configuration has diverged from remote ({git_sync_status.ahead} ahead, "
                f"{git_sync_status.behind} behind). Reconcile Git history before pushing."
            )

    if repository_type == "s3":
        b_label = f" '{s3_bucket_name}'" if s3_bucket_name else ""
        if s3_bucket_exists is False:
            warnings.append(f"Configured S3 bucket{b_label} does not exist.")
        elif s3_bucket_accessible is False:
            warnings.append(
                f"Access denied or connection failure to configured S3 bucket{b_label}."
            )
        elif s3_bucket_exists is True and s3_object_exists is False:
            warnings.append(
                f"Configuration archive is not present in S3 bucket{b_label}. "
                "Run 'lza config push' to upload local configuration."
            )


    elif repository_type == "codecommit":
        if codecommit_exists is False:
            warnings.append("Configured CodeCommit repository does not exist.")
        elif codecommit_accessible is False:
            warnings.append("Access denied or connection failure to CodeCommit repository.")
        elif codecommit_exists is True and codecommit_branch_exists is False:
            warnings.append(
                "Configured branch does not exist in CodeCommit repository. "
                "Run 'lza config push' to push branch."
            )
    elif repository_type == "codeconnection":
        if codeconnection_status == "PENDING":
            warnings.append(
                "CodeConnection is in PENDING status. Complete the handshake in the AWS Console."
            )
        elif codeconnection_status in {"ERROR", "NOT_FOUND", "INACCESSIBLE"}:
            warnings.append(f"CodeConnection issue detected (Status: {codeconnection_status}).")

    if pipeline_status == "Failed":
        detail = ""
        if pipeline_failed_stage and pipeline_failed_action:
            detail = f" (Stage: '{pipeline_failed_stage}', Action: '{pipeline_failed_action}')"
        elif pipeline_failed_stage:
            detail = f" (Stage: '{pipeline_failed_stage}')"
        warnings.append(
            f"Latest execution of configuration pipeline '{pipeline_name}' failed{detail}."
        )
    elif pipeline_status == "Cancelled":
        warnings.append(
            f"Latest execution of configuration pipeline '{pipeline_name}' was cancelled."
        )

    return tuple(warnings)




def get_config_status_workflow(
    *,
    target_dir: Path | None = None,
    config: WorkspaceConfig | None = None,
    state: WorkspaceState | None = None,
    workspace_dir: Path | None = None,
) -> ConfigurationStatusResult:
    """Query workspace configuration and remote/pipeline status data."""
    if config is not None and workspace_dir is not None:
        resolved_workspace_dir = workspace_dir
        resolved_config = config
        resolved_state = state
    else:
        ctx = load_workspace_context(
            target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED
        )
        resolved_workspace_dir = ctx.workspace_dir
        resolved_config = ctx.config
        resolved_state = ctx.state

    config_dir = resolved_workspace_dir / resolved_config.configuration.local_path
    yaml_files = (
        tuple(
            sorted(
                file.name
                for file in config_dir.iterdir()
                if file.is_file() and file.suffix in (".yaml", ".yml")
            )
        )
        if config_dir.exists()
        else ()
    )
    repo = resolved_config.configuration.repository

    profile = resolved_config.aws.profile or ""
    aws_context = resolve_aws_execution_context(
        profile=profile,
        region=resolved_config.aws.region,
        role_arn=resolved_config.aws.role_arn,
        expected_account_id=resolved_config.aws.account_id,
    )
    factory = aws_context.factory
    region = aws_context.region
    aws_identity = aws_context.identity
    aws_error = aws_context.error
    account_id = aws_identity["account"] if aws_identity else "UNKNOWN_ACCOUNT"

    initialized_at = resolved_state.config_initialized_at if resolved_state else None
    template_name = resolved_state.config_template_name if resolved_state else None
    template_source = resolved_state.config_template_source if resolved_state else None
    drifted_fields: tuple[str, ...] = ()
    has_init_state = bool(
        resolved_state
        and resolved_state.config_initialized_at
        and resolved_state.config_init_values
    )
    if has_init_state and resolved_state and resolved_state.config_init_values:
        current_snapshot = capture_init_values_snapshot(resolved_config)
        saved_snapshot = resolved_state.config_init_values
        drifted_fields = tuple(
            sorted(k for k, v in current_snapshot.items() if saved_snapshot.get(k) != v)
        )

    # Git working tree and remote synchronization
    git_working_tree = get_git_working_tree_status(config_dir)
    git_sync_status = (
        get_git_remote_sync_status(config_dir, branch=repo.branch)
        if git_working_tree
        else None
    )

    # Remote source inspection
    s3_bucket_name = None
    s3_bucket_exists = None
    s3_bucket_accessible = None
    s3_bucket_versioning = None
    s3_bucket_encryption = None
    s3_object_exists = None
    s3_object_etag = None
    s3_object_version_id = None
    s3_object_last_modified = None
    s3_object_size = None
    s3_error = None

    codecommit_exists = None
    codecommit_accessible = None
    codecommit_branch_exists = None
    codecommit_error = None

    codeconnection_status = None
    codeconnection_provider = None
    codeconnection_owner_account = None
    codeconnection_error = None

    if repo.type == "s3":
        s3_bucket_name = repo.bucket
        if not s3_bucket_name:
            acc_id = (
                resolved_config.aws.account_id
                or (resolved_state.management_account_id if resolved_state else None)
                or (aws_identity.get("account") if aws_identity else None)
            )
            reg = region or resolved_config.aws.region
            if acc_id and reg:
                s3_bucket_name = get_canonical_config_s3_bucket(acc_id, reg)

        if s3_bucket_name and aws_identity:

            try:
                s3_client = factory.get_client("s3")
                b_info = inspect_s3_bucket(client=s3_client, bucket_name=s3_bucket_name)
                s3_bucket_exists = b_info.get("exists")
                s3_bucket_accessible = b_info.get("accessible")
                s3_bucket_versioning = b_info.get("versioning_enabled")
                s3_bucket_encryption = b_info.get("encryption_enabled")

                if s3_bucket_exists:
                    p = repo.prefix
                    prefix_clean = (
                        p if p.endswith("/") else f"{p}/"
                        if p
                        else ""
                    )
                    key_path = f"{prefix_clean}{repo.key or 'aws-accelerator-config.zip'}"
                    obj_info = inspect_s3_object_safe(
                        client=s3_client, bucket_name=s3_bucket_name, object_key=key_path
                    )
                    s3_object_exists = obj_info.get("exists")
                    s3_object_etag = obj_info.get("etag")
                    s3_object_version_id = obj_info.get("version_id")
                    s3_object_last_modified = obj_info.get("last_modified")
                    s3_object_size = obj_info.get("content_length")
                    s3_error = obj_info.get("error")
            except Exception as exc:
                s3_error = str(exc)
                s3_bucket_accessible = False



    elif repo.type == "codecommit":
        repo_name = repo.repository_name or "aws-accelerator-config"
        branch_name = repo.branch or "main"
        if aws_identity:
            try:
                cc_client = factory.get_client("codecommit")
                cc_info = inspect_codecommit_config_repository(
                    client=cc_client, repository_name=repo_name, branch_name=branch_name
                )
                codecommit_exists = cc_info.get("exists")
                codecommit_accessible = cc_info.get("accessible")
                codecommit_branch_exists = cc_info.get("branch_exists")
            except Exception as exc:
                codecommit_error = str(exc)
                codecommit_accessible = False

    elif repo.type == "codeconnection":
        if repo.codeconnection_arn and aws_identity:
            conn_res = inspect_codeconnection(
                connection_arn=repo.codeconnection_arn,
                factory=factory,
            )
            codeconnection_status = conn_res.status
            codeconnection_provider = conn_res.provider_type
            codeconnection_owner_account = conn_res.owner_account_id
            codeconnection_error = conn_res.error

    # Configuration Pipeline Status
    prefix = resolved_config.lza.accelerator_prefix or "AWSAccelerator"
    config_pipeline_name = resolved_config.pipelines.configuration.name or f"{prefix}-Pipeline"
    config_pipeline_arn = (
        f"arn:aws:codepipeline:{region}:{account_id}:{config_pipeline_name}"
    )

    pipeline_status: str | None = None
    pipeline_execution_id: str | None = None
    pipeline_failed_stage: str | None = None
    pipeline_failed_action: str | None = None
    pipeline_failed_build_url: str | None = None
    pipeline_error: str | None = None
    pipeline_state: PipelineStateResult | None = None

    if resolved_state and resolved_state.config_pipeline_status:
        pipeline_status = resolved_state.config_pipeline_status
        pipeline_execution_id = resolved_state.config_pipeline_execution_id
        pipeline_failed_stage = resolved_state.config_pipeline_failed_stage
        pipeline_failed_action = resolved_state.config_pipeline_failed_action
        pipeline_failed_build_url = resolved_state.config_pipeline_failed_build_url
        pipeline_error = resolved_state.config_pipeline_error
    elif aws_identity:
        codepipeline_client = factory.get_client("codepipeline")
        pipeline_state = get_pipeline_state(
            client=codepipeline_client, pipeline_name=config_pipeline_name
        )
        if pipeline_state.exists and pipeline_state.status != "NOT_CHECKED":
            pipeline_status = pipeline_state.status
            pipeline_execution_id = (
                resolved_state.config_pipeline_execution_id if resolved_state else None
            ) or pipeline_state.latest_execution_id
            if pipeline_state.status in {"Failed", "Cancelled"}:
                for st in pipeline_state.stage_states:
                    if st.status == "Failed":
                        pipeline_failed_stage = st.stage_name
                        for act in st.actions:
                            if act.status == "Failed":
                                pipeline_failed_action = act.action_name
                                pipeline_failed_build_url = act.external_execution_url
                                if act.external_execution_id:
                                    diags = fetch_codebuild_diagnostics(
                                        factory=factory,
                                        build_id=act.external_execution_id,
                                    )
                                    if diags:
                                        pipeline_error = "\n".join(diags)
                                if not pipeline_error:
                                    pipeline_error = act.error_message or act.summary
                                break
                        break
    elif resolved_state and resolved_state.config_pipeline_execution_id:
        pipeline_execution_id = resolved_state.config_pipeline_execution_id

    warnings = _compile_warnings(
        config_dir_exists=config_dir.exists(),
        drifted_fields=drifted_fields,
        git_working_tree=git_working_tree,
        git_sync_status=git_sync_status,
        repository_type=repo.type,
        s3_bucket_name=s3_bucket_name,
        s3_bucket_exists=s3_bucket_exists,

        s3_bucket_accessible=s3_bucket_accessible,
        s3_object_exists=s3_object_exists,
        codecommit_exists=codecommit_exists,
        codecommit_accessible=codecommit_accessible,
        codecommit_branch_exists=codecommit_branch_exists,
        codeconnection_status=codeconnection_status,
        pipeline_name=config_pipeline_name,
        pipeline_status=pipeline_status,
        pipeline_failed_stage=pipeline_failed_stage,
        pipeline_failed_action=pipeline_failed_action,
    )

    return ConfigurationStatusResult(
        workspace_dir=resolved_workspace_dir,
        customer_name=resolved_config.customer.name,
        lza_version=resolved_config.lza.version,
        profile=profile,
        region=region,
        aws_identity=aws_identity,
        aws_error=aws_error,
        config_dir=config_dir,
        config_dir_exists=config_dir.exists(),
        yaml_files=yaml_files,
        repository_type=repo.type,
        repository_bucket=s3_bucket_name if repo.type == "s3" else repo.bucket,
        repository_prefix=repo.prefix,
        repository_key=repo.key,

        repository_name=repo.repository_name,
        repository_branch=repo.branch,
        codeconnection_arn=repo.codeconnection_arn,
        owner=repo.owner,
        repository_url=repo.repository,
        initialized_at=initialized_at,
        template_name=template_name,
        template_source=template_source,
        drifted_fields=drifted_fields,
        git_working_tree=git_working_tree,
        git_sync_status=git_sync_status,
        s3_bucket_exists=s3_bucket_exists,
        s3_bucket_accessible=s3_bucket_accessible,
        s3_bucket_versioning=s3_bucket_versioning,
        s3_bucket_encryption=s3_bucket_encryption,
        s3_object_exists=s3_object_exists,
        s3_object_etag=s3_object_etag,
        s3_object_version_id=s3_object_version_id,
        s3_object_last_modified=s3_object_last_modified,
        s3_object_size=s3_object_size,
        s3_error=s3_error,
        codecommit_exists=codecommit_exists,
        codecommit_accessible=codecommit_accessible,
        codecommit_branch_exists=codecommit_branch_exists,
        codecommit_error=codecommit_error,
        codeconnection_status=codeconnection_status,
        codeconnection_provider=codeconnection_provider,
        codeconnection_owner_account=codeconnection_owner_account,
        codeconnection_error=codeconnection_error,
        pipeline_name=config_pipeline_name,
        pipeline_arn=config_pipeline_arn,
        pipeline_status=pipeline_status,
        pipeline_execution_id=pipeline_execution_id,
        pipeline_failed_stage=pipeline_failed_stage,
        pipeline_failed_action=pipeline_failed_action,
        pipeline_failed_build_url=pipeline_failed_build_url,
        pipeline_error=pipeline_error,
        pipeline_state=pipeline_state,
        uploaded_at=resolved_state.config_uploaded_at if resolved_state else None,
        downloaded_at=resolved_state.config_downloaded_at if resolved_state else None,
        artifact_etag=resolved_state.config_artifact_etag if resolved_state else None,
        artifact_version_id=resolved_state.config_artifact_version_id if resolved_state else None,
        has_state=resolved_state is not None,
        warnings=warnings,
    )



__all__ = [
    "ConfigurationStatusResult",
    "get_config_status_workflow",
]


