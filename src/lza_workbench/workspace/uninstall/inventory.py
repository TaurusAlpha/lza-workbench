"""Inventory discovery engine for LZA solution uninstallation."""

from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path
from typing import TYPE_CHECKING

from ruamel.yaml import YAML

from lza_workbench.configuration.validation import parse_yaml_file
from lza_workbench.errors import LzaError
from lza_workbench.infrastructure.aws.cloudformation import (
    get_stack_resources,
    list_matching_stacks,
)
from lza_workbench.infrastructure.aws.organizations import list_organization_accounts
from lza_workbench.infrastructure.aws.s3 import list_buckets_by_prefix
from lza_workbench.infrastructure.aws.session import AwsExecutionContext

if TYPE_CHECKING:
    from lza_workbench.workspace.context import WorkspaceContext
from lza_workbench.workspace.uninstall.models import (
    UninstallAccountTarget,
    UninstallOptions,
    UninstallPlan,
    UninstallRetainedResource,
    UninstallS3Bucket,
    UninstallStack,
)


def resolve_target_regions(
    context: WorkspaceContext,
    execution_context: AwsExecutionContext,
    options: UninstallOptions,
) -> list[str]:
    """Resolve target regions from options, global-config.yaml, or AWS."""
    if options.regions:
        return sorted({r.strip() for r in options.regions if r.strip()})

    if options.all_regions:
        try:
            ec2 = execution_context.factory.get_client("ec2")
            resp = ec2.describe_regions(AllRegions=False)
            return sorted(r["RegionName"] for r in resp.get("Regions", []))
        except Exception as exc:
            raise LzaError(f"Failed to query AWS regions: {exc}") from exc

    # Default to global-config.yaml
    global_config_path = context.config_dir / "global-config.yaml"
    if not global_config_path.is_file():
        alt_path = context.config_dir / "global-config.yml"
        if alt_path.is_file():
            global_config_path = alt_path

    if global_config_path.is_file():
        try:
            data = parse_yaml_file(global_config_path)
            if isinstance(data, dict):
                regions: set[str] = set()
                home_region = data.get("homeRegion")
                if home_region and isinstance(home_region, str):
                    regions.add(home_region.strip())
                enabled = data.get("enabledRegions", [])
                if isinstance(enabled, list):
                    for r in enabled:
                        if isinstance(r, str):
                            regions.add(r.strip())
                if regions:
                    return sorted(regions)
        except Exception:
            pass

    # Fallback to workspace AWS region
    fallback = context.config.aws.region or "us-east-1"
    return [fallback]


def _load_accounts_from_profiles_file(
    profiles_file: str,
    mgmt_account_id: str,
    assume_role_name: str,
) -> list[UninstallAccountTarget]:
    path = Path(profiles_file)
    if not path.is_file():
        raise LzaError(f"Profiles file not found: {profiles_file}")

    try:
        content = path.read_text(encoding="utf-8")
        if path.suffix in (".yaml", ".yml"):
            yaml = YAML(typ="safe")
            data = yaml.load(content)
        else:
            data = json.loads(content)

        if not isinstance(data, list):
            raise LzaError("Profiles file must contain a list of account/profile mappings")

        targets: list[UninstallAccountTarget] = []
        for item in data:
            if isinstance(item, dict):
                acc_id = str(item.get("account_id") or item.get("account") or "").strip()
                prof = str(item.get("profile") or "").strip() or None
                name = str(item.get("name") or acc_id or "Account")
                if acc_id:
                    targets.append(
                        UninstallAccountTarget(
                            account_id=acc_id,
                            name=name,
                            is_management=(acc_id == mgmt_account_id),
                            profile=prof,
                            role_name=assume_role_name,
                        )
                    )
        return targets
    except Exception as exc:
        raise LzaError(f"Failed to read profiles file '{profiles_file}': {exc}") from exc


def _discover_organization_accounts(
    execution_context: AwsExecutionContext,
    mgmt_account_id: str,
    account_filter: list[str],
    assume_role_name: str,
) -> list[UninstallAccountTarget]:
    try:
        org_client = execution_context.factory.get_client("organizations")
        org_accounts = list_organization_accounts(client=org_client)
        if not org_accounts:
            return []

        filter_set = set(account_filter) if account_filter else None
        targets: list[UninstallAccountTarget] = []
        for acc in org_accounts:
            acc_id = acc["Id"]
            name = acc["Name"]
            if filter_set and acc_id not in filter_set and name not in filter_set:
                continue
            targets.append(
                UninstallAccountTarget(
                    account_id=acc_id,
                    name=name,
                    is_management=(acc_id == mgmt_account_id),
                    role_name=assume_role_name,
                )
            )
        return targets
    except Exception:
        return []


def resolve_target_accounts(
    context: WorkspaceContext,
    execution_context: AwsExecutionContext,
    options: UninstallOptions,
) -> list[UninstallAccountTarget]:
    """Resolve target accounts via profiles file, AWS Organizations, or workspace default."""
    mgmt_account_id = (
        context.config.aws.account_id
        or (execution_context.identity.get("account") if execution_context.identity else None)
        or ""
    )

    # 1. Custom profiles file
    if options.profiles_file:
        targets = _load_accounts_from_profiles_file(
            options.profiles_file, mgmt_account_id, options.assume_role_name
        )
        if targets:
            return targets

    # 2. AWS Organizations discovery
    org_targets = _discover_organization_accounts(
        execution_context, mgmt_account_id, options.accounts, options.assume_role_name
    )
    if org_targets:
        return org_targets

    # 3. Fallback to current workspace account
    if mgmt_account_id:
        return [
            UninstallAccountTarget(
                account_id=mgmt_account_id,
                name=context.config.customer.name or "Management",
                is_management=True,
                profile=context.config.aws.profile,
            )
        ]

    raise LzaError("Could not resolve any target AWS accounts for uninstall.")



def _inspect_account_region(
    account: UninstallAccountTarget,
    region: str,
    execution_context: AwsExecutionContext,
    accelerator_prefix: str,
    options: UninstallOptions,
) -> tuple[list[UninstallStack], list[UninstallRetainedResource], list[UninstallS3Bucket]]:
    """Inspect stacks, retained resources, and S3 buckets for one (account, region) pair."""
    # Build client factory for target account & region
    if account.profile:
        factory = execution_context.factory.for_profile(account.profile, region=region)
    elif account.is_management:
        factory = execution_context.factory.for_region(region)
    else:
        role_name = account.role_name or options.assume_role_name
        factory = execution_context.factory.for_account(account.account_id, role_name=role_name, region=region)

    discovered_stacks: list[UninstallStack] = []
    discovered_retained: list[UninstallRetainedResource] = []
    discovered_buckets: list[UninstallS3Bucket] = []

    # 1. CloudFormation stacks
    try:
        cfn_client = factory.get_client("cloudformation")
        raw_stacks = list_matching_stacks(
            client=cfn_client,
            prefix=accelerator_prefix,
            account_id=account.account_id,
            region=region,
        )

        for s in raw_stacks:
            stack_name = s.get("StackName", "")
            is_pipeline_or_installer = stack_name in (
                "AWSAccelerator-PipelineStack",
                "AWSAccelerator-InstallerStack",
            ) or stack_name.endswith(("-InstallerStack", "-PipelineStack"))

            if is_pipeline_or_installer:
                if options.skip_pipeline and "Pipeline" in stack_name:
                    continue
                if options.skip_installer and "Installer" in stack_name:
                    continue

            term_protection = bool(s.get("EnableTerminationProtection", False))
            creation_time = s.get("CreationTime")

            # Retained resources
            retained_list: list[UninstallRetainedResource] = []
            try:
                resources = get_stack_resources(client=cfn_client, stack_name=stack_name)
                for res in resources:
                    if res.get("IsRetained"):
                        retained_item = UninstallRetainedResource(
                            account_id=account.account_id,
                            region=region,
                            stack_name=stack_name,
                            logical_id=str(res.get("LogicalResourceId", "")),
                            physical_id=str(res.get("PhysicalResourceId", "")),
                            resource_type=str(res.get("ResourceType", "")),
                            action_status="RETAINED",
                        )
                        retained_list.append(retained_item)
                        discovered_retained.append(retained_item)
            except Exception:
                pass

            discovered_stacks.append(
                UninstallStack(
                    stack_name=stack_name,
                    account_id=account.account_id,
                    account_name=account.name,
                    region=region,
                    creation_time=creation_time,
                    termination_protection=term_protection,
                    is_pipeline_or_installer=is_pipeline_or_installer,
                    retained_resources=retained_list,
                )
            )
    except Exception:
        # Graceful inspection failure for inaccessible accounts/regions
        pass

    # 2. S3 buckets
    try:
        s3_client = factory.get_client("s3")
        prefixes_to_check = {accelerator_prefix.lower().rstrip("-"), "aws-accelerator"}
        found_bucket_names: set[str] = set()
        for pfx in prefixes_to_check:
            names = list_buckets_by_prefix(
                client=s3_client,
                prefix=pfx,
                account_id=account.account_id,
                region=region,
            )
            found_bucket_names.update(names)

        for b_name in sorted(found_bucket_names):
            discovered_buckets.append(
                UninstallS3Bucket(
                    bucket_name=b_name,
                    account_id=account.account_id,
                    region=region,
                    action_status="RETAINED",
                )
            )
    except Exception:
        pass

    return discovered_stacks, discovered_retained, discovered_buckets


def sort_stacks_in_reverse_deployment_order(
    stacks: list[UninstallStack],
    mgmt_account_id: str,
) -> list[UninstallStack]:
    """Sort stacks in dependency-safe reverse deployment order.

    Order:
      1. Member account stacks: newest first (CreationTime descending).
      2. Management account workload and stage stacks: newest first.
      3. AWSAccelerator-PipelineStack.
      4. AWSAccelerator-InstallerStack.
    """
    member_stacks: list[UninstallStack] = []
    mgmt_stage_stacks: list[UninstallStack] = []
    pipeline_stacks: list[UninstallStack] = []
    installer_stacks: list[UninstallStack] = []

    for s in stacks:
        if "Pipeline" in s.stack_name:
            pipeline_stacks.append(s)
        elif "Installer" in s.stack_name:
            installer_stacks.append(s)
        elif s.account_id != mgmt_account_id:
            member_stacks.append(s)
        else:
            mgmt_stage_stacks.append(s)

    # Sort each group by creation_time descending (newest first)
    member_stacks.sort(
        key=lambda x: x.creation_time.timestamp() if x.creation_time else 0,
        reverse=True,
    )
    mgmt_stage_stacks.sort(
        key=lambda x: x.creation_time.timestamp() if x.creation_time else 0,
        reverse=True,
    )

    return member_stacks + mgmt_stage_stacks + pipeline_stacks + installer_stacks


def build_uninstall_plan(
    *,
    context: WorkspaceContext,
    execution_context: AwsExecutionContext,
    options: UninstallOptions,
) -> UninstallPlan:
    """Discover all LZA resources and assemble an ordered UninstallPlan."""
    accelerator_prefix = context.config.lza.accelerator_prefix or "AWSAccelerator"
    regions = resolve_target_regions(context, execution_context, options)
    accounts = resolve_target_accounts(context, execution_context, options)

    all_stacks: list[UninstallStack] = []
    all_retained: list[UninstallRetainedResource] = []
    all_buckets: list[UninstallS3Bucket] = []

    tasks = [(acc, reg) for acc in accounts for reg in regions]

    with concurrent.futures.ThreadPoolExecutor(max_workers=options.max_workers) as executor:
        future_to_task = {
            executor.submit(
                _inspect_account_region,
                acc,
                reg,
                execution_context,
                accelerator_prefix,
                options,
            ): (acc, reg)
            for acc, reg in tasks
        }

        for future in concurrent.futures.as_completed(future_to_task):
            try:
                stacks, retained, buckets = future.result()
                all_stacks.extend(stacks)
                all_retained.extend(retained)
                all_buckets.extend(buckets)
            except Exception:
                pass

    mgmt_account_id = (
        context.config.aws.account_id
        or (execution_context.identity.get("account") if execution_context.identity else None)
        or ""
    )
    ordered_stacks = sort_stacks_in_reverse_deployment_order(all_stacks, mgmt_account_id)

    return UninstallPlan(
        customer_name=context.config.customer.name,
        customer_slug=context.config.customer.slug,
        accelerator_prefix=accelerator_prefix,
        accounts=accounts,
        regions=regions,
        stacks=ordered_stacks,
        retained_resources=all_retained,
        s3_buckets=all_buckets,
    )


__all__ = [
    "build_uninstall_plan",
    "resolve_target_accounts",
    "resolve_target_regions",
    "sort_stacks_in_reverse_deployment_order",
]
