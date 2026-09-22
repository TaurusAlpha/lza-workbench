"""Status API adapter for the Web interface."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from lza_workbench.configuration.deploy import deploy_configuration_workflow
from lza_workbench.configuration.pull import (
    ConfigPullRequest,
    apply_config_pull,
    prepare_config_pull,
)
from lza_workbench.configuration.push import (
    ConfigPushRequest,
    apply_config_push,
    prepare_config_push,
)
from lza_workbench.configuration.status import get_config_status_workflow
from lza_workbench.errors import LzaError
from lza_workbench.installer.initialize import (
    InstallerSettingsRequest,
    apply_installer_settings,
    get_installer_parameters_schema,
)
from lza_workbench.installer.plan import plan_installer_workflow
from lza_workbench.installer.reset import reset_installer_settings
from lza_workbench.installer.status import get_installer_status_workflow
from lza_workbench.interfaces.web.context import ActiveWorkspaceContext
from lza_workbench.interfaces.web.serializers import (
    serialize_config_pull_preparation,
    serialize_config_pull_result,
    serialize_config_push_preparation,
    serialize_config_push_result,
    serialize_configuration_status,
    serialize_import_discovery,
    serialize_installer_plan,
    serialize_installer_status,
    serialize_pipeline_diagnostics,
    serialize_pipeline_snapshot,
    serialize_root_status,
    serialize_workspace_import_result,
    serialize_workspace_init_result,
)
from lza_workbench.pipeline.status import (
    get_pipeline_diagnostics_workflow,
    get_pipeline_snapshot_workflow,
)
from lza_workbench.status.observer import get_root_status_workflow
from lza_workbench.workspace.import_workspace import (
    ImportWorkspaceRequest,
    apply_workspace_import,
    discover_import_workspace,
    prepare_workspace_import,
)
from lza_workbench.workspace.initialize import init_workspace


class WorkspaceOpenPayload(BaseModel):
    directory: str


class WorkspaceInitPayload(BaseModel):
    customer_name: str
    workspace_dir: str | None = None
    aws_auth_type: str = "profile"
    aws_profile: str | None = None
    aws_role_arn: str | None = None
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


def _register_workspace_routes(router: APIRouter, context: ActiveWorkspaceContext) -> None:
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
        result = init_workspace(
            customer_name=payload.customer_name,
            workspace_dir=target_dir,
            aws_auth_type=payload.aws_auth_type,
            aws_profile=payload.aws_profile,
            aws_role_arn=payload.aws_role_arn,
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
        result = init_workspace(
            customer_name=payload.customer_name,
            workspace_dir=target_dir,
            aws_auth_type=payload.aws_auth_type,
            aws_profile=payload.aws_profile,
            aws_role_arn=payload.aws_role_arn,
            aws_region=payload.aws_region,
            lza_version=payload.lza_version,
            dry_run=False,
            force=payload.force,
            skip_aws_check=payload.skip_aws_check,
        )
        context.set_workspace_dir(result.workspace_dir)
        return serialize_workspace_init_result(result)


def _register_workspace_import_routes(router: APIRouter, context: ActiveWorkspaceContext) -> None:
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


def _register_status_routes(router: APIRouter, context: ActiveWorkspaceContext) -> None:
    @router.get("/api/status")
    def get_status() -> dict[str, Any]:
        return serialize_root_status(get_root_status_workflow(target_dir=context.require_workspace_dir()))

    @router.get("/api/status/config")
    def get_config_status() -> dict[str, Any]:
        status_res = get_config_status_workflow(target_dir=context.require_workspace_dir())
        return serialize_configuration_status(status_res)

    @router.get("/api/status/installer")
    def get_installer_status() -> dict[str, Any]:
        target = context.require_workspace_dir()
        status_res = get_installer_status_workflow(target_dir=target)
        form_res = get_installer_parameters_schema(target_dir=target, all_fields=True)
        return serialize_installer_status(status_res, form_res)


def _register_installer_routes(router: APIRouter, context: ActiveWorkspaceContext) -> None:
    @router.post("/api/installer/settings")
    def save_installer_settings(payload: InstallerSettingsPayload) -> dict[str, Any]:
        result = apply_installer_settings(
            InstallerSettingsRequest(target_dir=context.require_workspace_dir(), values=payload.values)
        )
        return {
            "success": True,
            "message": "Installer settings saved successfully.",
            "resolvedParameters": result.resolved_parameters,
        }

    @router.post("/api/installer/plan")
    def get_installer_plan() -> dict[str, Any]:
        return serialize_installer_plan(
            plan_installer_workflow(target_dir=context.require_workspace_dir(), dry_run=True)
        )

    @router.post("/api/installer/reset")
    def reset_installer_settings_endpoint() -> dict[str, Any]:
        result = reset_installer_settings(target_dir=context.require_workspace_dir())
        return {
            "success": True,
            "message": "Installer settings reset to deployed configuration.",
            "resolvedParameters": result.resolved_parameters,
        }


def _register_config_routes(router: APIRouter, context: ActiveWorkspaceContext) -> None:
    @router.post("/api/config/pull/prepare")
    def prepare_pull() -> dict[str, Any]:
        prep = prepare_config_pull(ConfigPullRequest(target_dir=context.require_workspace_dir()))
        return serialize_config_pull_preparation(prep)

    @router.post("/api/config/pull/apply")
    def apply_pull(payload: ConfigActionApplyPayload | None = None) -> dict[str, Any]:
        req = ConfigPullRequest(
            target_dir=context.require_workspace_dir(),
            overwrite_confirmed=payload.overwrite_confirmed if payload else False,
            force=payload.force if payload else False,
        )
        res = apply_config_pull(req)
        return serialize_config_pull_result(res)

    @router.post("/api/config/push/prepare")
    def prepare_push() -> dict[str, Any]:
        prep = prepare_config_push(ConfigPushRequest(target_dir=context.require_workspace_dir()))
        return serialize_config_push_preparation(prep)

    @router.post("/api/config/push/apply")
    def apply_push(payload: ConfigActionApplyPayload | None = None) -> dict[str, Any]:
        req = ConfigPushRequest(
            target_dir=context.require_workspace_dir(),
            overwrite_confirmed=payload.overwrite_confirmed if payload else False,
            force=payload.force if payload else False,
        )
        res = apply_config_push(req)
        return serialize_config_push_result(res)

    @router.post("/api/config/deploy")
    def apply_deploy(payload: ConfigActionApplyPayload | None = None) -> dict[str, Any]:
        deploy_res = deploy_configuration_workflow(
            target_dir=context.require_workspace_dir(),
            dry_run=False,
            force=payload.force if payload else False,
            overwrite_confirmed=payload.overwrite_confirmed if payload else False,
            watch=False,
        )
        push_data = (
            serialize_config_push_result(deploy_res.push_result) if deploy_res.push_result else None
        )
        pipeline_started = deploy_res.start_result is not None
        execution_id = deploy_res.start_result.execution_id if deploy_res.start_result else None
        pipeline_name = deploy_res.start_result.pipeline_name if deploy_res.start_result else None
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


def _register_pipeline_routes(router: APIRouter, context: ActiveWorkspaceContext) -> None:
    @router.get("/api/pipeline/snapshot")
    def pipeline_snapshot(
        type: str = "configuration",
        execution_id: str | None = None,
    ) -> dict[str, Any]:
        snapshot = get_pipeline_snapshot_workflow(
            target_dir=context.require_workspace_dir(),
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
            target_dir=context.require_workspace_dir(),
            pipeline_type=type,
            execution_id=execution_id,
        )
        return serialize_pipeline_diagnostics(failures)


def create_status_router(
    *, workspace_dir: Path | ActiveWorkspaceContext | None = None
) -> APIRouter:
    if isinstance(workspace_dir, ActiveWorkspaceContext):
        context = workspace_dir
    elif workspace_dir is not None:
        context = ActiveWorkspaceContext(workspace_dir)
    else:
        context = ActiveWorkspaceContext(None)

    router = APIRouter()

    _register_workspace_routes(router, context)
    _register_workspace_import_routes(router, context)
    _register_status_routes(router, context)
    _register_installer_routes(router, context)
    _register_config_routes(router, context)
    _register_pipeline_routes(router, context)

    return router


__all__ = [
    "ActiveWorkspaceContext",
    "create_status_router",
]
