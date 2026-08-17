"""Resolve and persist CloudFormation parameters for the LZA installer stack."""

from typing import Any

from lza_workbench.installer.versions import version_to_branch
from lza_workbench.workspace.schema import WorkspaceConfig

KNOWN_INSTALLER_PARAMETER_NAMES = frozenset(
    {
        "RepositorySource",
        "RepositoryOwner",
        "RepositoryName",
        "RepositoryBranchName",
        "EnableApprovalStage",
        "ApprovalStageNotifyEmailList",
        "ManagementAccountEmail",
        "LogArchiveAccountEmail",
        "AuditAccountEmail",
        "ControlTowerEnabled",
        "AcceleratorPrefix",
        "ConfigurationRepositoryLocation",
        "UseExistingConfigRepo",
        "ConfigCodeConnectionArn",
        "ExistingConfigRepositoryOwner",
        "ExistingConfigRepositoryName",
        "ExistingConfigRepositoryBranchName",
        "EnableDiagnosticsPack",
    }
)


def persist_template_defaults(config: WorkspaceConfig, schema: dict[str, dict[str, Any]]) -> bool:
    """Persist defaults for template parameters not represented in the workspace schema."""
    changed = False
    persisted = config.installer.template_parameters
    for key, definition in schema.items():
        if key in KNOWN_INSTALLER_PARAMETER_NAMES or key in persisted:
            continue
        if "Default" in definition:
            persisted[key] = str(definition["Default"])
            changed = True
    return changed


def apply_installer_parameter(config: WorkspaceConfig, parameter_name: str, value: str) -> None:
    """Persist an accepted template parameter in its owning workspace setting."""
    config.installer.template_parameters[parameter_name] = value
    source_code = config.installer.source_code
    options = config.installer.options

    if parameter_name == "RepositorySource":
        source_code.repository_type = value  # type: ignore[assignment]
    elif parameter_name == "RepositoryOwner":
        source_code.owner = value
    elif parameter_name == "RepositoryName":
        source_code.repository_name = value
    elif parameter_name == "RepositoryBranchName":
        source_code.branch = value
    elif parameter_name == "EnableApprovalStage":
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
    elif parameter_name == "AcceleratorPrefix":
        config.lza.accelerator_prefix = value
    elif parameter_name == "ConfigurationRepositoryLocation":
        config.configuration.repository.type = value  # type: ignore[assignment]
    elif parameter_name == "UseExistingConfigRepo":
        options.use_existing_config_repo = value == "Yes"
    elif parameter_name == "ConfigCodeConnectionArn":
        options.config_code_connection_arn = value or None
    elif parameter_name == "ExistingConfigRepositoryOwner":
        options.existing_config_repository_owner = value or None
    elif parameter_name == "ExistingConfigRepositoryName":
        options.existing_config_repository_name = value or None
    elif parameter_name == "ExistingConfigRepositoryBranchName":
        options.existing_config_repository_branch_name = value or None
    elif parameter_name == "EnableDiagnosticsPack":
        options.enable_diagnostics_pack = value == "Yes"


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

    branch = (source_code.branch or "").strip()
    if not branch:
        branch = version_to_branch(config.lza.version)

    enable_approval = options.enable_approval_stage
    notify_emails = ",".join(options.approval_stage_notify_email_list) if enable_approval else ""

    repo_source = source_code.repository_type
    repo_owner = source_code.owner if repo_source == "github" else ""

    config_location = repo_config.type or options.configuration_repository_location or "s3"
    use_existing = options.use_existing_config_repo

    if config_location == "s3":
        use_existing = False
        code_conn_arn = ""
        existing_owner = ""
        existing_name = ""
        existing_branch = ""
    elif config_location == "codeconnection":
        use_existing = True
        code_conn_arn = options.config_code_connection_arn or source_code.connection_arn or ""
        existing_owner = options.existing_config_repository_owner or ""
        existing_name = options.existing_config_repository_name or repo_config.repository_name or ""
        existing_branch = options.existing_config_repository_branch_name or repo_config.branch or ""
    elif config_location == "codecommit":
        code_conn_arn = ""
        existing_owner = ""
        if use_existing:
            existing_name = (
                options.existing_config_repository_name or repo_config.repository_name or ""
            )
            existing_branch = (
                options.existing_config_repository_branch_name or repo_config.branch or ""
            )
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
        "RepositoryBranchName": branch,
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
            if key in config.installer.template_parameters:
                params[key] = config.installer.template_parameters[key]
            elif "Default" in info:
                params[key] = str(info["Default"])

    for key, value in config.installer.template_parameters.items():
        if key in params:
            params[key] = value

    return params
