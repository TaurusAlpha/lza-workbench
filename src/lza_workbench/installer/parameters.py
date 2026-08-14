"""Build CloudFormation parameters for the LZA installer stack."""

from lza_workbench.installer.versions import version_to_branch
from lza_workbench.workspace.models import WorkspaceConfig


def build_installer_cfn_parameters(config: WorkspaceConfig) -> dict[str, str]:
    """Map workspace configuration into CloudFormation parameter key-value pairs."""
    source_code = config.installer.source_code
    options = config.installer.options
    repo_config = config.configuration.repository

    branch = (source_code.branch or "").strip()
    if not branch:
        branch = version_to_branch(config.lza.version)

    notify_emails = ",".join(options.approval_stage_notify_email_list)

    return {
        "RepositorySource": source_code.repository_type or "github",
        "RepositoryOwner": source_code.owner or "awslabs",
        "RepositoryName": source_code.repository_name or "landing-zone-accelerator-on-aws",
        "RepositoryBranchName": branch,
        "EnableApprovalStage": "Yes" if options.enable_approval_stage else "No",
        "ApprovalStageNotifyEmailList": notify_emails,
        "ManagementAccountEmail": options.management_account_email or "",
        "LogArchiveAccountEmail": options.log_archive_account_email or "",
        "AuditAccountEmail": options.audit_account_email or "",
        "ControlTowerEnabled": "Yes" if options.control_tower_enabled else "No",
        "AcceleratorPrefix": config.lza.accelerator_prefix or "AWSAccelerator",
        "ConfigurationRepositoryLocation": repo_config.type or "s3",
        "UseExistingConfigRepo": "Yes" if options.use_existing_config_repo else "No",
        "ConfigCodeConnectionArn": (
            options.config_code_connection_arn or source_code.connection_arn or ""
        ),
        "ExistingConfigRepositoryOwner": options.existing_config_repository_owner or "",
        "ExistingConfigRepositoryName": (
            options.existing_config_repository_name or repo_config.repository_name or ""
        ),
        "ExistingConfigRepositoryBranchName": (
            options.existing_config_repository_branch_name or repo_config.branch or ""
        ),
        "EnableDiagnosticsPack": "Yes" if options.enable_diagnostics_pack else "No",
    }
