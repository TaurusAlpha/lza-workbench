"""Focused stages for deploying an LZA installer CloudFormation stack."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lza_workbench.aws.client_factory import AwsClientFactory
from lza_workbench.aws.cloudformation import CfnDeploymentPlanResult
from lza_workbench.aws.codecommit import CodeCommitPlanResult, inspect_codecommit_repository
from lza_workbench.aws.s3 import inspect_s3_installer_source
from lza_workbench.errors import LzaError
from lza_workbench.installer.config import (
    InstallerConfigValidationResult,
    validate_installer_configuration,
)
from lza_workbench.installer.parameters import build_installer_cfn_parameters
from lza_workbench.installer.templates import (
    inspect_template_parameters,
    resolve_installer_template,
    validate_parameters_against_schema,
)
from lza_workbench.installer.versions import version_to_branch
from lza_workbench.workspace.models import WorkspaceConfig
from lza_workbench.workspace.state import load_workspace_state, write_workspace_state

SAFE_EXISTING_STACK_STATUSES = {
    "CREATE_COMPLETE",
    "UPDATE_COMPLETE",
    "UPDATE_ROLLBACK_COMPLETE",
}


class InstallerConfigValidationError(LzaError):
    """Raised when installer configuration is incomplete for deployment."""

    def __init__(self, validation: InstallerConfigValidationResult) -> None:
        self.validation = validation
        missing = ", ".join(f"{s.section}.{s.attribute}" for s in validation.missing_fields)
        super().__init__(
            f"{len(validation.missing_fields)} required parameter(s) missing from "
            f"lza-workspace.yaml ({missing}). "
            "Run 'lza installer plan' to resolve and configure missing values."
        )


def validate_deployment_preflight(config: WorkspaceConfig) -> InstallerConfigValidationResult:
    """Validate configuration required before any AWS deployment activity."""
    validation = validate_installer_configuration(config)
    if not validation.is_complete:
        raise InstallerConfigValidationError(validation)
    return validation


def prepare_installer_template(
    *, workspace_dir: Path, config: WorkspaceConfig, dry_run: bool
) -> tuple[Path, dict[str, str]]:
    """Resolve the template and parameters, validating them before AWS mutation."""
    template_path = resolve_installer_template(workspace_dir, config, dry_run=dry_run)
    params_schema = inspect_template_parameters(template_path)
    resolved_parameters = build_installer_cfn_parameters(config)
    validate_parameters_against_schema(resolved_parameters, params_schema)
    return template_path, resolved_parameters


def inspect_installer_source(
    *, factory: AwsClientFactory, config: WorkspaceConfig, region: str
) -> CodeCommitPlanResult | None:
    """Inspect the configured installer source and enforce its deployment prerequisite.

    CodeCommit synchronization is deliberately a manual prerequisite. Creating an empty
    repository cannot satisfy the installer pipeline, which needs the selected LZA branch.
    """
    source = config.installer.source_code
    if source.repository_type == "codecommit":
        version_ref = version_to_branch(config.lza.version)
        plan = inspect_codecommit_repository(
            factory=factory,
            repository_type=source.repository_type,
            repository_name=source.repository_name,
            branch_name=source.branch,
            version_ref=version_ref,
            region=region,
        )
        if plan.status != "INITIALIZED":
            raise LzaError(
                "CodeCommit source is a manual prerequisite: repository "
                f"'{plan.repository_name}' must contain branch '{plan.branch_name}' before "
                "installer deployment. Run 'lza installer plan' for the required source actions."
            )
        return plan

    if source.repository_type == "s3":
        inspect_s3_installer_source(
            factory=factory,
            bucket_name=source.bucket or "",
            object_key=source.key or "",
        )
    return None


def validate_cloudformation_plan(plan: CfnDeploymentPlanResult) -> str:
    """Return a safe mutation operation or reject an unknown/unsafe stack state."""
    if plan.operation == "CREATE" and plan.stack_status is None:
        return "CREATE"
    if (
        plan.operation in {"UPDATE", "NO_CHANGE"}
        and plan.stack_status in SAFE_EXISTING_STACK_STATUSES
    ):
        return "UPDATE" if plan.operation == "UPDATE" else "NO_CHANGE"
    raise LzaError(
        "Refusing CloudFormation deployment because the stack state is unsafe or unknown: "
        f"operation={plan.operation}, status={plan.stack_status or 'not found'}."
    )


def update_successful_deployment_state(
    *,
    workspace_dir: Path,
    aws_identity: dict[str, str],
    stack_id: str,
    stack_status: str,
) -> None:
    """Persist operational state only after a successful CloudFormation deployment."""
    state = load_workspace_state(workspace_dir)
    now = datetime.now(UTC)
    state.management_account_id = aws_identity["account"]
    state.caller_arn = aws_identity["arn"]
    state.installer_stack_id = stack_id
    state.installer_stack_status = stack_status
    state.installer_stack_updated_at = now
    state.updated_at = now
    write_workspace_state(workspace_dir, state)
