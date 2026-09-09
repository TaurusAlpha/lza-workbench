"""Resolve and persist CloudFormation parameters for the LZA installer stack."""

from typing import Any

from lza_workbench.configuration.schema import get_canonical_config_s3_bucket
from lza_workbench.installer.versions import version_to_branch
from lza_workbench.workspace.schema import WorkspaceConfig

INSTALLER_PARAMETER_LABELS = {
    "RepositorySource": "Source location",
    "RepositoryOwner": "Repository owner",
    "RepositoryName": "Repository name",
    "RepositoryBranchName": "Branch name",
    "RepositoryBucketName": "Source S3 bucket",
    "RepositoryBucketObject": "Source S3 object key",
    "EnableApprovalStage": "Enable approval stage",
    "ApprovalStageNotifyEmailList": "Approval notification emails",
    "ManagementAccountEmail": "Management account email",
    "LogArchiveAccountEmail": "Log Archive account email",
    "AuditAccountEmail": "Security Audit account email",
    "ControlTowerEnabled": "Control Tower environment",
    "AcceleratorPrefix": "Accelerator resource name prefix",
    "ConfigurationRepositoryLocation": "Configuration repository location",
    "UseExistingConfigRepo": "Use existing configuration repository",
    "ConfigCodeConnectionArn": "CodeConnection ARN",
    "ExistingConfigRepositoryOwner": "Existing config repository owner",
    "ExistingConfigRepositoryName": "Existing config repository name",
    "ExistingConfigRepositoryBranchName": "Existing config repository branch",
    "EnableDiagnosticsPack": "Enable diagnostics pack",
}


def get_installer_parameter_label(
    parameter_name: str, definition: dict[str, Any] | None = None
) -> str:
    """Return a concise prompt label for an installer template parameter."""
    if parameter_name in INSTALLER_PARAMETER_LABELS:
        return INSTALLER_PARAMETER_LABELS[parameter_name]
    if definition:
        label = definition.get("Label") or definition.get("Description")
        if label:
            cleaned = str(label).strip()
            if ". " in cleaned:
                cleaned = cleaned.split(". ")[0].rstrip(".")
            if len(cleaned) <= 60:
                return cleaned
    return parameter_name


def resolve_installer_source_branch(
    repository_type: str, branch: str | None, lza_version: str | None
) -> str:
    """Return the configured source branch or the source-specific default."""
    if configured_branch := (branch or "").strip():
        return configured_branch
    if repository_type == "github":
        return version_to_branch(lza_version)
    return "main"


UNSUPPORTED_INSTALLER_PARAMETERS: frozenset[str] = frozenset({
    "ConfigurationRepositoryLocation",
    "UseExistingConfigRepo",
    "ConfigCodeConnectionArn",
    "ExistingConfigRepositoryOwner",
    "ExistingConfigRepositoryName",
    "ExistingConfigRepositoryBranchName",
})


def is_installer_parameter_applicable(config: WorkspaceConfig, parameter_name: str) -> bool:
    """Return whether a template parameter applies to the current configuration."""
    source_type = config.installer.source_code.repository_type
    approval_enabled = config.installer.options.enable_approval_stage

    if parameter_name == "RepositoryOwner":
        return source_type == "github"

    if parameter_name in {"RepositoryName", "RepositoryBranchName"}:
        return source_type in {"github", "codecommit", "codeconnection"}

    if parameter_name in {"RepositoryBucketName", "RepositoryBucketObject"}:
        return source_type == "s3"

    if parameter_name == "ApprovalStageNotifyEmailList":
        return bool(approval_enabled)

    if parameter_name in UNSUPPORTED_INSTALLER_PARAMETERS:
        return False

    return True


def _apply_source_code_parameter(
    config: WorkspaceConfig, parameter_name: str, value: str
) -> bool:
    source_code = config.installer.source_code
    if parameter_name == "RepositorySource":
        source_code.repository_type = value  # type: ignore[assignment]
    elif parameter_name == "RepositoryOwner":
        source_code.owner = value
    elif parameter_name == "RepositoryName":
        source_code.repository_name = value
    elif parameter_name == "RepositoryBranchName":
        source_code.branch = value if value else version_to_branch(config.lza.version)
    elif parameter_name == "RepositoryBucketName":
        source_code.bucket = value or None
    elif parameter_name == "RepositoryBucketObject":
        source_code.key = value or None
    else:
        return False
    return True


def _apply_options_parameter(
    config: WorkspaceConfig, parameter_name: str, value: str
) -> bool:
    options = config.installer.options
    if parameter_name == "EnableApprovalStage":
        options.enable_approval_stage = value == "Yes"
    elif parameter_name == "ApprovalStageNotifyEmailList":
        options.approval_stage_notify_email_list = [
            email.strip() for email in value.split(",") if email
        ]
    elif parameter_name == "ManagementAccountEmail":
        options.management_account_email = value
    elif parameter_name == "LogArchiveAccountEmail":
        options.log_archive_account_email = value
    elif parameter_name == "AuditAccountEmail":
        options.audit_account_email = value
    elif parameter_name == "ControlTowerEnabled":
        options.control_tower_enabled = value == "Yes"
    elif parameter_name == "EnableDiagnosticsPack":
        options.enable_diagnostics_pack = value == "Yes"
    else:
        return False
    return True


def _apply_config_repo_parameter(
    config: WorkspaceConfig, parameter_name: str, value: str
) -> bool:
    repo = config.configuration.repository
    if parameter_name == "ConfigurationRepositoryLocation":
        repo.type = value  # type: ignore[assignment]
    elif parameter_name == "ConfigCodeConnectionArn":
        repo.codeconnection_arn = value or None
    elif parameter_name == "ExistingConfigRepositoryOwner":
        repo.owner = value or None
    elif parameter_name == "ExistingConfigRepositoryName":
        repo.repository_name = value or None
    elif parameter_name == "ExistingConfigRepositoryBranchName":
        repo.branch = value or None
    else:
        return False
    return True


def apply_installer_parameter(config: WorkspaceConfig, parameter_name: str, value: str) -> None:
    """Persist an accepted template parameter in its owning workspace setting."""
    if _apply_source_code_parameter(config, parameter_name, value):
        return
    if _apply_options_parameter(config, parameter_name, value):
        return
    if _apply_config_repo_parameter(config, parameter_name, value):
        return

    if parameter_name == "AcceleratorPrefix":
        config.lza.accelerator_prefix = value
    elif parameter_name == "UseExistingConfigRepo":
        return
    else:
        config.installer.extra_parameters[parameter_name] = value


def apply_deployed_installer_parameters(
    config: WorkspaceConfig,
    parameters: dict[str, str],
    *,
    stack_id: str | None = None,
) -> None:
    """Apply observed installer parameters to their owning workspace settings."""
    if not parameters:
        return

    if not config.aws.account_id and stack_id and ":stack/" in stack_id:
        arn_parts = stack_id.split(":")
        if len(arn_parts) >= 5 and arn_parts[4].isdigit():
            config.aws.account_id = arn_parts[4]

    for parameter_name, value in parameters.items():
        apply_installer_parameter(config, parameter_name, value)

    repository = config.configuration.repository
    if (
        repository.type == "s3"
        and not repository.bucket
        and config.aws.account_id
        and config.aws.region
    ):
        repository.bucket = get_canonical_config_s3_bucket(config.aws.account_id, config.aws.region)

def build_installer_cfn_parameters(
    config: WorkspaceConfig, schema: dict[str, dict[str, Any]] | None = None
) -> dict[str, str]:
    """Map workspace configuration into CloudFormation parameter key-value pairs.

    Optionally accepts a template parameter schema to collect additional parameters
    and apply template defaults for missing parameters.
    """
    source_code = config.installer.source_code
    options = config.installer.options
    repo_config = config.configuration.repository

    branch = source_code.branch
    enable_approval = options.enable_approval_stage
    notify_emails = ",".join(options.approval_stage_notify_email_list) if enable_approval else ""

    repo_source = source_code.repository_type
    repo_owner = source_code.owner if repo_source == "github" else ""

    config_location = repo_config.type
    use_existing = config_location in {"codecommit", "codeconnection"}

    if config_location == "s3":
        use_existing = False
        code_conn_arn = ""
        existing_owner = ""
        existing_name = ""
        existing_branch = ""
    elif config_location == "codeconnection":
        use_existing = True
        code_conn_arn = repo_config.codeconnection_arn or ""
        existing_owner = repo_config.owner or ""
        existing_name = repo_config.repository_name or ""
        existing_branch = repo_config.branch or ""
    elif config_location == "codecommit":
        code_conn_arn = ""
        existing_owner = ""
        if use_existing:
            existing_name = repo_config.repository_name or "lza-config-source"
            existing_branch = repo_config.branch or "main"
        else:
            existing_name = ""
            existing_branch = ""
    else:
        code_conn_arn = ""
        existing_owner = ""
        existing_name = ""
        existing_branch = ""

    params: dict[str, str] = {
        "RepositorySource": repo_source,
        "RepositoryOwner": repo_owner,
        "RepositoryName": source_code.repository_name or "landing-zone-accelerator-on-aws",
        "RepositoryBranchName": branch or "",
        "EnableApprovalStage": "Yes" if enable_approval else "No",
        "ApprovalStageNotifyEmailList": notify_emails,
        "ManagementAccountEmail": options.management_account_email or "",
        "LogArchiveAccountEmail": options.log_archive_account_email or "",
        "AuditAccountEmail": options.audit_account_email or "",
        "ControlTowerEnabled": "Yes" if options.control_tower_enabled else "No",
        "AcceleratorPrefix": config.lza.accelerator_prefix or "AWSAccelerator",
        "ConfigurationRepositoryLocation": config_location,
        "UseExistingConfigRepo": "Yes" if use_existing else "No",
        "ConfigCodeConnectionArn": code_conn_arn,
        "ExistingConfigRepositoryOwner": existing_owner,
        "ExistingConfigRepositoryName": existing_name,
        "ExistingConfigRepositoryBranchName": existing_branch,
        "EnableDiagnosticsPack": "Yes" if options.enable_diagnostics_pack else "No",
    }

    if schema:
        for key, info in schema.items():
            if key in params:
                continue
            if key in config.installer.extra_parameters:
                params[key] = config.installer.extra_parameters[key]
            elif "Default" in info:
                params[key] = str(info["Default"])

    return params
