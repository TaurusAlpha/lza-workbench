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
    UninstallTarget,
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
    target = UninstallTarget(
        customer_name="Test",
        customer_slug="test",
        management_account_id="066949449104",
        management_profile="boj-opswat",
    )

    class DummyExecContext:
        identity = {"account": "066949449104"}
        account_id = "066949449104"
        class Factory:
            pass
        factory = Factory()

    targets = resolve_target_accounts(target, DummyExecContext(), options)  # type: ignore

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

    write_retained_resources_to_state(ws_dir, records, status="in_progress")

    loaded = read_retained_resources_from_state(ws_dir)
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

    target = UninstallTarget(
        customer_name="Acme",
        customer_slug="acme",
        management_account_id="111111111111",
        home_region="eu-west-1",
        management_profile="acme-mgmt",
        workspace_dir=ws_dir,
    )

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
    write_retained_resources_to_state(ws_dir, records)

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
        account_id = "111111111111"
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
        target=target,
        execution_context=MockExecContext(),  # type: ignore
        selected_physical_ids=["/aws/accelerator/test"],
        account_targets=account_targets,
    )

    assert deleted_calls == ["/aws/accelerator/test"]
    assert len(updated) == 2
    assert updated[0].status == "deleted"
    assert updated[1].status == "retained"

    # Confirm persisted to disk
    persisted = read_retained_resources_from_state(ws_dir)
    assert persisted[0].status == "deleted"
    assert persisted[1].status == "retained"


def test_execute_uninstall_requires_record_dir_without_workspace() -> None:
    import pytest

    from lza_workbench.errors import LzaError
    from lza_workbench.workspace.uninstall.executor import execute_uninstall

    target = UninstallTarget(
        customer_name="Acme",
        customer_slug="acme",
        management_account_id="111111111111",
    )
    plan = UninstallPlan(
        customer_name="Acme",
        customer_slug="acme",
        accelerator_prefix="AWSAccelerator",
        accounts=[],
        regions=["eu-west-1"],
        stacks=[],
        retained_resources=[],
        s3_buckets=[],
    )

    class DummyExecContext:
        identity = {"account": "111111111111"}
        account_id = "111111111111"
        factory = None

    with pytest.raises(LzaError, match="record directory"):
        execute_uninstall(
            target=target,
            execution_context=DummyExecContext(),  # type: ignore
            plan=plan,
            options=UninstallOptions(dry_run=False, force=True),
        )


def test_execute_uninstall_persists_records_in_record_dir_before_stack_deletion(
    tmp_path: Path,
) -> None:
    from unittest.mock import patch

    from lza_workbench.workspace.uninstall.executor import (
        execute_uninstall,
        load_or_init_progress,
    )
    from lza_workbench.workspace.uninstall.retained import read_retained_resources_from_state

    record_dir = tmp_path / "uninstall-records"
    target = UninstallTarget(
        customer_name="Acme",
        customer_slug="acme",
        management_account_id="111111111111",
        record_dir=record_dir,
    )
    plan = UninstallPlan(
        customer_name="Acme",
        customer_slug="acme",
        accelerator_prefix="AWSAccelerator",
        accounts=[
            UninstallAccountTarget(account_id="111111111111", name="Mgmt", is_management=True)
        ],
        regions=["eu-west-1"],
        stacks=[
            UninstallStack(
                stack_name="AWSAccelerator-Stage",
                account_id="111111111111",
                account_name="Mgmt",
                region="eu-west-1",
            )
        ],
        retained_resources=[
            UninstallRetainedResource(
                account_id="111111111111",
                region="eu-west-1",
                stack_name="AWSAccelerator-Stage",
                logical_id="LogGroup1",
                physical_id="/aws/accelerator/test",
                resource_type="AWS::Logs::LogGroup",
            )
        ],
        s3_buckets=[],
    )

    class MockFactory:
        def for_region(self, region: str) -> MockFactory:
            return self

        def get_client(self, service: str) -> object:
            return object()

    class MockExecContext:
        identity = {"account": "111111111111"}
        account_id = "111111111111"
        factory = MockFactory()

    def verify_saved_before_delete(*, client: object, stack_name: str) -> None:
        del client, stack_name
        saved_retained = read_retained_resources_from_state(target)
        assert len(saved_retained) == 1
        assert saved_retained[0].physical_id == "/aws/accelerator/test"
        saved_progress = load_or_init_progress(target)
        assert saved_progress.status == "IN_PROGRESS"
        assert len(saved_progress.retained_resources_remaining) == 1

    with patch(
        "lza_workbench.workspace.uninstall.executor.delete_cloudformation_stack",
        side_effect=verify_saved_before_delete,
    ):
        progress = execute_uninstall(
            target=target,
            execution_context=MockExecContext(),  # type: ignore
            plan=plan,
            options=UninstallOptions(dry_run=False, force=True),
        )

    assert progress.status == "COMPLETED"
    assert progress.deleted_stacks == ["AWSAccelerator-Stage"]
    assert (record_dir / "uninstall-progress.json").is_file()
    assert (record_dir / "retained-resources.json").is_file()


def test_execute_uninstall_restart_preserves_retained_inventory_from_deleted_stacks(
    tmp_path: Path,
) -> None:
    from unittest.mock import patch

    from lza_workbench.workspace.uninstall.executor import execute_uninstall
    from lza_workbench.workspace.uninstall.retained import read_retained_resources_from_state

    record_dir = tmp_path / "uninstall-records"
    target = UninstallTarget(
        customer_name="Acme",
        customer_slug="acme",
        management_account_id="111111111111",
        record_dir=record_dir,
    )
    initial_plan = UninstallPlan(
        customer_name="Acme",
        customer_slug="acme",
        accelerator_prefix="AWSAccelerator",
        accounts=[
            UninstallAccountTarget(account_id="111111111111", name="Mgmt", is_management=True)
        ],
        regions=["eu-west-1"],
        stacks=[
            UninstallStack(
                stack_name="AWSAccelerator-Stage1",
                account_id="111111111111",
                account_name="Mgmt",
                region="eu-west-1",
            ),
            UninstallStack(
                stack_name="AWSAccelerator-Stage2",
                account_id="111111111111",
                account_name="Mgmt",
                region="eu-west-1",
            ),
        ],
        retained_resources=[
            UninstallRetainedResource(
                account_id="111111111111",
                region="eu-west-1",
                stack_name="AWSAccelerator-Stage1",
                logical_id="LogGroup1",
                physical_id="/aws/accelerator/stage1",
                resource_type="AWS::Logs::LogGroup",
            ),
            UninstallRetainedResource(
                account_id="111111111111",
                region="eu-west-1",
                stack_name="AWSAccelerator-Stage2",
                logical_id="LogGroup2",
                physical_id="/aws/accelerator/stage2",
                resource_type="AWS::Logs::LogGroup",
            ),
        ],
        s3_buckets=[],
    )

    class MockFactory:
        def for_region(self, region: str) -> MockFactory:
            return self

        def get_client(self, service: str) -> object:
            return object()

    class MockExecContext:
        identity = {"account": "111111111111"}
        account_id = "111111111111"
        factory = MockFactory()

    # Run 1: deletes Stage1, then crashes before Stage2
    def delete_then_interrupt(*, client: object, stack_name: str) -> None:
        del client
        if stack_name == "AWSAccelerator-Stage2":
            raise RuntimeError("Simulated process interruption")

    with (
        patch(
            "lza_workbench.workspace.uninstall.executor.delete_cloudformation_stack",
            side_effect=delete_then_interrupt,
        ),
        pytest.raises(RuntimeError, match="Simulated process interruption"),
    ):
        execute_uninstall(
            target=target,
            execution_context=MockExecContext(),  # type: ignore
            plan=initial_plan,
            options=UninstallOptions(dry_run=False, force=True),
        )

    # Run 2: fresh discovery no longer sees Stage1 or its retained resource
    restarted_plan = UninstallPlan(
        customer_name="Acme",
        customer_slug="acme",
        accelerator_prefix="AWSAccelerator",
        accounts=[
            UninstallAccountTarget(account_id="111111111111", name="Mgmt", is_management=True)
        ],
        regions=["eu-west-1"],
        stacks=[
            UninstallStack(
                stack_name="AWSAccelerator-Stage2",
                account_id="111111111111",
                account_name="Mgmt",
                region="eu-west-1",
            ),
        ],
        retained_resources=[
            UninstallRetainedResource(
                account_id="111111111111",
                region="eu-west-1",
                stack_name="AWSAccelerator-Stage2",
                logical_id="LogGroup2",
                physical_id="/aws/accelerator/stage2",
                resource_type="AWS::Logs::LogGroup",
            ),
        ],
        s3_buckets=[],
    )

    with (
        patch("lza_workbench.workspace.uninstall.executor.delete_cloudformation_stack"),
        patch("lza_workbench.workspace.uninstall.retained.delete_log_group") as mock_del_log,
    ):
        progress = execute_uninstall(
            target=target,
            execution_context=MockExecContext(),  # type: ignore
            plan=restarted_plan,
            options=UninstallOptions(
                dry_run=False, force=True, delete_retained_resources=True
            ),
        )

    saved_retained = read_retained_resources_from_state(target)
    assert {r.physical_id for r in saved_retained} == {
        "/aws/accelerator/stage1",
        "/aws/accelerator/stage2",
    }
    assert all(r.status == "deleted" for r in saved_retained)
    assert mock_del_log.call_count == 2
    assert {item["physical_id"] for item in progress.deleted_retained} == {
        "/aws/accelerator/stage1",
        "/aws/accelerator/stage2",
    }
    assert progress.retained_resources_remaining == []


def test_execute_uninstall_marks_failed_when_bucket_or_retained_deletion_fails(
    tmp_path: Path,
) -> None:
    from unittest.mock import patch

    from lza_workbench.workspace.uninstall.executor import execute_uninstall
    from lza_workbench.workspace.uninstall.state import UninstallState

    record_dir = tmp_path / "uninstall-failure-records"
    target = UninstallTarget(
        customer_name="Acme",
        customer_slug="acme",
        management_account_id="111111111111",
        record_dir=record_dir,
    )
    plan = UninstallPlan(
        customer_name="Acme",
        customer_slug="acme",
        accelerator_prefix="AWSAccelerator",
        accounts=[
            UninstallAccountTarget(account_id="111111111111", name="Mgmt", is_management=True)
        ],
        regions=["eu-west-1"],
        stacks=[],
        retained_resources=[
            UninstallRetainedResource(
                account_id="111111111111",
                region="eu-west-1",
                stack_name="AWSAccelerator-Stage",
                logical_id="FailLog",
                physical_id="/aws/accelerator/fail",
                resource_type="AWS::Logs::LogGroup",
            ),
            UninstallRetainedResource(
                account_id="111111111111",
                region="eu-west-1",
                stack_name="AWSAccelerator-Stage",
                logical_id="KeepLog",
                physical_id="/aws/accelerator/keep",
                resource_type="AWS::Logs::LogGroup",
            ),
        ],
        s3_buckets=[
            UninstallS3Bucket(
                bucket_name="aws-accelerator-fail-bucket",
                account_id="111111111111",
                region="eu-west-1",
            )
        ],
    )

    class MockFactory:
        def for_region(self, region: str) -> MockFactory:
            return self

        def get_client(self, service: str) -> object:
            return object()

    class MockExecContext:
        identity = {"account": "111111111111"}
        account_id = "111111111111"
        factory = MockFactory()

    with (
        patch(
            "lza_workbench.workspace.uninstall.executor.empty_and_delete_s3_bucket",
            side_effect=RuntimeError("Bucket access denied"),
        ),
        patch(
            "lza_workbench.workspace.uninstall.retained.delete_log_group",
            side_effect=RuntimeError("LogGroup access denied"),
        ),
    ):
        progress = execute_uninstall(
            target=target,
            execution_context=MockExecContext(),  # type: ignore
            plan=plan,
            options=UninstallOptions(
                dry_run=False,
                force=True,
                delete_s3_buckets=True,
                delete_retained_resources=True,
            ),
            selected_retained_ids=["/aws/accelerator/fail"],
        )

    assert progress.status == "FAILED"
    assert len(progress.failed_buckets) == 1
    assert progress.failed_buckets[0]["bucket_name"] == "aws-accelerator-fail-bucket"
    assert len(progress.failed_retained) == 1
    assert progress.failed_retained[0]["physical_id"] == "/aws/accelerator/fail"
    assert len(progress.retained_resources_remaining) == 1
    assert progress.retained_resources_remaining[0]["physical_id"] == "/aws/accelerator/keep"

    persisted = UninstallState.model_validate_json(
        (record_dir / "retained-resources.json").read_text(encoding="utf-8")
    )
    assert persisted.status == "failed"




