"""Tests for workspace uninstallation models and ordering logic."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lza_workbench.workspace.uninstall.inventory import (
    resolve_target_accounts,
    sort_stacks_in_reverse_deployment_order,
)
from lza_workbench.workspace.uninstall.models import (
    UninstallAccountTarget,
    UninstallOptions,
    UninstallPlan,
    UninstallRetainedResource,
    UninstallS3Bucket,
    UninstallStack,
)


def test_sort_stacks_in_reverse_deployment_order() -> None:
    mgmt_account = "111111111111"
    member_account = "222222222222"

    t1 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 1, 1, 11, 0, 0, tzinfo=UTC)
    t3 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    stacks = [
        UninstallStack(
            stack_name="AWSAccelerator-InstallerStack",
            account_id=mgmt_account,
            account_name="Management",
            region="eu-west-1",
            creation_time=t1,
            is_pipeline_or_installer=True,
        ),
        UninstallStack(
            stack_name="AWSAccelerator-PipelineStack",
            account_id=mgmt_account,
            account_name="Management",
            region="eu-west-1",
            creation_time=t2,
            is_pipeline_or_installer=True,
        ),
        UninstallStack(
            stack_name="AWSAccelerator-Security-111111111111-eu-west-1",
            account_id=mgmt_account,
            account_name="Management",
            region="eu-west-1",
            creation_time=t3,
        ),
        UninstallStack(
            stack_name="AWSAccelerator-Network-222222222222-eu-west-1",
            account_id=member_account,
            account_name="Workload",
            region="eu-west-1",
            creation_time=t1,
        ),
        UninstallStack(
            stack_name="AWSAccelerator-Workload-222222222222-eu-west-1",
            account_id=member_account,
            account_name="Workload",
            region="eu-west-1",
            creation_time=t3,
        ),
    ]

    ordered = sort_stacks_in_reverse_deployment_order(stacks, mgmt_account_id=mgmt_account)

    stack_names = [s.stack_name for s in ordered]

    # Member account stacks should be first, newest first
    assert stack_names[0] == "AWSAccelerator-Workload-222222222222-eu-west-1"
    assert stack_names[1] == "AWSAccelerator-Network-222222222222-eu-west-1"

    # Then management stage stack
    assert stack_names[2] == "AWSAccelerator-Security-111111111111-eu-west-1"

    # Then PipelineStack
    assert stack_names[3] == "AWSAccelerator-PipelineStack"

    # Finally InstallerStack is last
    assert stack_names[4] == "AWSAccelerator-InstallerStack"

    # Even with empty/unresolved mgmt_account_id, Pipeline and Installer stacks remain last
    ordered_unknown = sort_stacks_in_reverse_deployment_order(stacks, mgmt_account_id="")
    names_unknown = [s.stack_name for s in ordered_unknown]
    assert names_unknown[-2] == "AWSAccelerator-PipelineStack"
    assert names_unknown[-1] == "AWSAccelerator-InstallerStack"


def test_uninstall_plan_counts() -> None:
    plan = UninstallPlan(
        customer_name="Test Customer",
        customer_slug="test-customer",
        accelerator_prefix="AWSAccelerator",
        accounts=[
            UninstallAccountTarget(account_id="111111111111", name="Mgmt", is_management=True)
        ],
        regions=["eu-west-1", "eu-central-1"],
        stacks=[
            UninstallStack(
                stack_name="AWSAccelerator-Stage",
                account_id="111111111111",
                account_name="Mgmt",
                region="eu-west-1",
                termination_protection=True,
            ),
            UninstallStack(
                stack_name="AWSAccelerator-PipelineStack",
                account_id="111111111111",
                account_name="Mgmt",
                region="eu-west-1",
                termination_protection=False,
            ),
        ],
        retained_resources=[
            UninstallRetainedResource(
                account_id="111111111111",
                region="eu-west-1",
                stack_name="AWSAccelerator-Stage",
                logical_id="Key1",
                physical_id="arn:aws:kms:...",
                resource_type="AWS::KMS::Key",
            )
        ],
        s3_buckets=[
            UninstallS3Bucket(
                bucket_name="aws-accelerator-logs-111111111111-eu-west-1",
                account_id="111111111111",
                region="eu-west-1",
            )
        ],
    )

    assert plan.total_stacks == 2
    assert plan.protected_stacks == 1
    assert plan.total_retained_resources == 1
    assert plan.total_s3_buckets == 1


def test_resolve_target_accounts_from_profiles_file(tmp_path: Path) -> None:
    profiles_file = tmp_path / "profiles.json"
    profiles_file.write_text(
        """[
            {"profile": "boj-opswat", "account_id": "066949449104", "name": "OpsWat"},
            {"profile": "boj-network", "account_id": "741448948161", "name": "Network"}
        ]""",
        encoding="utf-8",
    )

    options = UninstallOptions(profiles_file=str(profiles_file))

    class DummyContext:
        class Config:
            class Aws:
                account_id = "066949449104"
                profile = "boj-opswat"
            aws = Aws()
            class Customer:
                name = "Test"
            customer = Customer()
        config = Config()

    class DummyExecContext:
        identity = {"account": "066949449104"}
        class Factory:
            pass
        factory = Factory()

    targets = resolve_target_accounts(DummyContext(), DummyExecContext(), options)  # type: ignore

    assert len(targets) == 2
    assert targets[0].account_id == "066949449104"
    assert targets[0].is_management is True
    assert targets[0].profile == "boj-opswat"
    assert targets[1].account_id == "741448948161"
    assert targets[1].is_management is False


def test_retained_resources_state_persistence(tmp_path: Path) -> None:
    from lza_workbench.workspace.persistence import write_workspace_config, write_workspace_state
    from lza_workbench.workspace.schema import (
        AwsConfig,
        CustomerConfig,
        WorkspaceConfig,
        WorkspaceState,
    )
    from lza_workbench.workspace.uninstall.retained import (
        read_retained_resources_from_state,
        write_retained_resources_to_state,
    )
    from lza_workbench.workspace.uninstall.state import RetainedResourceRecord

    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    config = WorkspaceConfig(
        customer=CustomerConfig(name="Acme", slug="acme"),
        aws=AwsConfig(region="eu-west-1", profile="acme-mgmt", account_id="111111111111"),
    )
    write_workspace_config(ws_dir, config)
    write_workspace_state(ws_dir, WorkspaceState())

    class MockContext:
        workspace_dir = ws_dir

    records = [
        RetainedResourceRecord(
            account_id="111111111111",
            region="eu-west-1",
            stack_name="AWSAccelerator-Security",
            logical_id="KmsKey",
            physical_id="arn:aws:kms:eu-west-1:111111111111:key/1234",
            resource_type="AWS::KMS::Key",
            status="retained",
        )
    ]

    write_retained_resources_to_state(MockContext(), records, status="in_progress")  # type: ignore

    loaded = read_retained_resources_from_state(MockContext())  # type: ignore
    assert len(loaded) == 1
    assert loaded[0].physical_id == "arn:aws:kms:eu-west-1:111111111111:key/1234"
    assert loaded[0].status == "retained"


def test_delete_selected_retained_resources_with_profile(tmp_path: Path) -> None:
    from lza_workbench.workspace.persistence import write_workspace_config, write_workspace_state
    from lza_workbench.workspace.schema import (
        AwsConfig,
        CustomerConfig,
        WorkspaceConfig,
        WorkspaceState,
    )
    from lza_workbench.workspace.uninstall.models import UninstallAccountTarget
    from lza_workbench.workspace.uninstall.retained import (
        delete_selected_retained_resources,
        read_retained_resources_from_state,
        write_retained_resources_to_state,
    )
    from lza_workbench.workspace.uninstall.state import RetainedResourceRecord

    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    ws_config = WorkspaceConfig(
        customer=CustomerConfig(name="Acme", slug="acme"),
        aws=AwsConfig(region="eu-west-1", profile="acme-mgmt", account_id="111111111111"),
    )
    write_workspace_config(ws_dir, ws_config)
    write_workspace_state(ws_dir, WorkspaceState())

    class MockContext:
        workspace_dir = ws_dir
        config = ws_config

    records = [
        RetainedResourceRecord(
            account_id="222222222222",
            region="eu-west-1",
            stack_name="AWSAccelerator-Logging",
            logical_id="LogGroup1",
            physical_id="/aws/accelerator/test",
            resource_type="AWS::Logs::LogGroup",
            status="retained",
        ),
        RetainedResourceRecord(
            account_id="222222222222",
            region="eu-west-1",
            stack_name="AWSAccelerator-Logging",
            logical_id="LogGroup2",
            physical_id="/aws/accelerator/keep",
            resource_type="AWS::Logs::LogGroup",
            status="retained",
        ),
    ]
    write_retained_resources_to_state(MockContext(), records)  # type: ignore

    deleted_calls: list[str] = []

    class MockLogsClient:
        def delete_log_group(self, logGroupName: str) -> None:
            deleted_calls.append(logGroupName)

    class MockFactory:
        def for_profile(self, profile: str, region: str | None = None) -> MockFactory:
            assert profile == "acme-workload"
            return self

        def get_client(self, service: str) -> MockLogsClient:
            assert service == "logs"
            return MockLogsClient()

    class MockExecContext:
        identity = {"account": "111111111111"}
        factory = MockFactory()

    account_targets = [
        UninstallAccountTarget(
            account_id="222222222222",
            name="Workload",
            profile="acme-workload",
        )
    ]

    # Delete only LogGroup1
    updated = delete_selected_retained_resources(
        context=MockContext(),  # type: ignore
        execution_context=MockExecContext(),  # type: ignore
        selected_physical_ids=["/aws/accelerator/test"],
        account_targets=account_targets,
    )

    assert deleted_calls == ["/aws/accelerator/test"]
    assert len(updated) == 2
    assert updated[0].status == "deleted"
    assert updated[1].status == "retained"

    # Confirm persisted to disk
    persisted = read_retained_resources_from_state(MockContext())  # type: ignore
    assert persisted[0].status == "deleted"
    assert persisted[1].status == "retained"


