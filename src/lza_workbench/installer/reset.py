"""Reset installer settings to current deployed configuration."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.errors import LzaError
from lza_workbench.infrastructure.aws.cloudformation import get_cloudformation_stack_status
from lza_workbench.infrastructure.aws.session import resolve_aws_execution_context
from lza_workbench.installer.initialize import (
    InstallerSettingsResult,
    _ensure_canonical_s3_bucket,
    _validate_candidate,
)
from lza_workbench.installer.parameters import (
    apply_deployed_installer_parameters,
    build_installer_cfn_parameters,
)
from lza_workbench.installer.state import (
    record_installer_observation,
    record_installer_template,
)
from lza_workbench.installer.templates import (
    inspect_template_parameters,
    resolve_installer_template,
)
from lza_workbench.installer.versions import (
    normalize_lza_version,
    resolve_deployed_installer_version,
)
from lza_workbench.workspace.context import load_workspace_context
from lza_workbench.workspace.persistence import update_workspace_state, write_workspace_config
from lza_workbench.workspace.schema import WorkspaceState
from lza_workbench.workspace.validation import WorkspaceCapability


def reset_installer_settings(*, target_dir: Path | None = None) -> InstallerSettingsResult:
    ctx = load_workspace_context(
        target_dir, required_capabilities=(WorkspaceCapability.METADATA_VALID,)
    )

    stack_name = (ctx.config.installer.stack_name or "AWSAccelerator-InstallerStack").strip()
    deployed_params: dict[str, str] | None = None
    stack_id: str | None = None
    stack_status: str | None = None
    deployed_version: str | None = None
    account_id: str | None = None
    live_discovered = False

    # 1. Try querying live AWS CloudFormation stack
    try:
        aws_context = resolve_aws_execution_context(
            profile=ctx.config.aws.profile,
            region=ctx.config.aws.region,
            role_arn=ctx.config.aws.role_arn,
            expected_account_id=ctx.config.aws.account_id,
            prime_credentials=ctx.config.aws.prime_credentials,
            require_identity=False,
        )
        account_id = aws_context.identity.get("account") if aws_context.identity else None
        cfn_client = aws_context.factory.get_client("cloudformation")
        cfn_status = get_cloudformation_stack_status(client=cfn_client, stack_name=stack_name)
        if cfn_status.exists and cfn_status.deployed_parameters:
            live_discovered = True
            deployed_params = dict(cfn_status.deployed_parameters)
            stack_id = cfn_status.stack_id
            stack_status = cfn_status.stack_status
            ssm_client = aws_context.factory.get_client("ssm")
            deployed_version = resolve_deployed_installer_version(
                cfn_client=cfn_client,
                ssm_client=ssm_client,
                stack_name=stack_name,
                accelerator_prefix=(
                    cfn_status.deployed_parameters.get("AcceleratorPrefix")
                    or ctx.config.lza.accelerator_prefix
                ),
            )
    except Exception:
        # Fall back to recorded state if live AWS query fails or credentials unavailable
        pass

    # 2. Fall back to recorded deployed state
    obs = ctx.state.installer.observation if ctx.state else None
    if not deployed_params and obs and obs.deployed_parameters:
        deployed_params = dict(obs.deployed_parameters)
        stack_id = obs.stack_id
        stack_status = obs.stack_status
        deployed_version = obs.deployed_version or (
            ctx.state.installer.template.version if ctx.state else None
        )

    if not deployed_params:
        raise LzaError(
            "Cannot reset installer settings: No deployed CloudFormation stack parameters found."
        )

    # 3. Apply deployed parameters to configuration candidate
    candidate = ctx.config.model_copy(deep=True)
    apply_deployed_installer_parameters(candidate, deployed_params, stack_id=stack_id)
    if deployed_version:
        candidate.lza.version = normalize_lza_version(deployed_version)

    _ensure_canonical_s3_bucket(candidate, ctx.state.observed_account_id if ctx.state else None)
    candidate = _validate_candidate(candidate)

    # 4. Resolve template and schema parameters
    template_path = resolve_installer_template(ctx.workspace_dir, candidate, dry_run=False)
    schema = inspect_template_parameters(template_path)
    resolved_parameters = build_installer_cfn_parameters(candidate, schema=schema)

    # 5. Persist to lza-workspace.yaml and update recorded state under file lock
    write_workspace_config(ctx.workspace_dir, candidate)
    if ctx.state is not None:
        def _record_reset(current: WorkspaceState) -> None:
            if live_discovered:
                record_installer_observation(
                    current,
                    account_id=account_id,
                    stack_name=stack_name,
                    stack_id=stack_id,
                    stack_status=stack_status,
                    deployed_version=deployed_version,
                    deployed_parameters=deployed_params,
                )
            record_installer_template(current, version=candidate.lza.version)

        _record_reset(ctx.state)
        update_workspace_state(ctx.workspace_dir, _record_reset)

    return InstallerSettingsResult(
        workspace_dir=ctx.workspace_dir,
        config=candidate,
        template_path=template_path,
        resolved_parameters=resolved_parameters,
        dry_run=False,
        no_save=False,
    )


__all__ = ["reset_installer_settings"]
