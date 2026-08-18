"""Focused stages for deploying an LZA installer CloudFormation stack."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.aws.client_factory import AwsClientFactory
from lza_workbench.aws.cloudformation import CfnDeploymentPlanResult
from lza_workbench.aws.codecommit import CodeCommitPlanResult, inspect_codecommit_repository
from lza_workbench.aws.s3 import inspect_s3_installer_source
from lza_workbench.aws.secrets_manager import inspect_github_secret_token
from lza_workbench.errors import LzaError
from lza_workbench.installer.config import (
    InstallerConfigValidationResult,
    validate_installer_configuration,
)
from lza_workbench.installer.parameters import (
    build_installer_cfn_parameters,
    resolve_installer_source_branch,
)
from lza_workbench.installer.templates import (
    inspect_template_parameters,
    resolve_installer_template,
    validate_parameters_against_schema,
)
from lza_workbench.workspace.schema import WorkspaceConfig

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


def validate_deployment_preflight(config: WorkspaceConfig) -> None:
    """Validate workspace installer settings before executing deployment mutations."""
    validation = validate_installer_configuration(config)
    if not validation.is_complete:
        raise InstallerConfigValidationError(validation)


def prepare_installer_template(
    *, workspace_dir: Path, config: WorkspaceConfig, dry_run: bool
) -> tuple[Path, dict[str, str]]:
    """Resolve and validate the local template and its parameters against the schema."""
    template_path = resolve_installer_template(workspace_dir, config, dry_run=dry_run)
    schema = inspect_template_parameters(template_path)
    parameters = build_installer_cfn_parameters(config, schema=schema)
    validate_parameters_against_schema(parameters, schema)
    return template_path, parameters


def inspect_installer_source(
    *,
    factory: AwsClientFactory,
    config: WorkspaceConfig,
    region: str,
) -> CodeCommitPlanResult | None:
    """Validate required remote source preconditions for installer CloudFormation."""
    source = config.installer.source_code
    if source.repository_type == "codecommit":
        version_ref = resolve_installer_source_branch(
            source.repository_type, source.branch, config.lza.version
        )
        plan = inspect_codecommit_repository(
            factory=factory,
            repository_type="codecommit",
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
    elif source.repository_type == "github":
        inspect_github_secret_token(factory=factory, secret_name=source.github_secret_name)
        return None
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


__all__ = [
    "InstallerConfigValidationError",
    "SAFE_EXISTING_STACK_STATUSES",
    "inspect_installer_source",
    "prepare_installer_template",
    "validate_cloudformation_plan",
    "validate_deployment_preflight",
]
