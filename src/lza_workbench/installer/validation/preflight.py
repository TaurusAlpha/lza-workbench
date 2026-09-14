"""Installer deployment preflight and CloudFormation plan safety checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lza_workbench.errors import LzaError
from lza_workbench.infrastructure.aws.cloudformation import CfnDeploymentPlanResult
from lza_workbench.installer.validation.config import (
    InstallerConfigValidationError,
    validate_installer_configuration,
)

if TYPE_CHECKING:
    from lza_workbench.workspace.schema import WorkspaceConfig

SAFE_EXISTING_STACK_STATUSES = {
    "CREATE_COMPLETE",
    "UPDATE_COMPLETE",
    "UPDATE_ROLLBACK_COMPLETE",
    "ROLLBACK_COMPLETE",
}

SAFE_CREATE_STACK_STATUSES = {"ROLLBACK_COMPLETE", "DELETE_COMPLETE", None}


def validate_deployment_preflight(config: WorkspaceConfig) -> None:
    """Validate workspace installer settings before executing deployment mutations."""
    validation = validate_installer_configuration(config)
    if not validation.is_complete:
        raise InstallerConfigValidationError(validation)


def validate_cloudformation_plan(plan: CfnDeploymentPlanResult) -> str:
    """Return a safe mutation operation or reject an unknown/unsafe stack state."""
    if plan.stack_status == "ROLLBACK_COMPLETE":
        return "CREATE"
    if (
        plan.operation in {"CREATE", "NO_CHANGE"}
        and plan.stack_status in SAFE_CREATE_STACK_STATUSES
    ):
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


__all__ = [
    "SAFE_CREATE_STACK_STATUSES",
    "SAFE_EXISTING_STACK_STATUSES",
    "validate_cloudformation_plan",
    "validate_deployment_preflight",
]
