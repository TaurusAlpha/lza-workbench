"""Tests for pipeline failure interpretation, normalization, and root-cause selection."""

from __future__ import annotations

from unittest.mock import MagicMock

from lza_workbench.pipeline.failures import (
    FailureCategory,
    FailureDiagnostic,
    clean_raw_diagnostic_text,
    collect_pipeline_action_failures,
    deduplicate_failure_diagnostics,
    interpret_failure_diagnostic,
    normalize_root_cause_and_resource,
    select_root_cause,
)


def test_clean_raw_diagnostic_text_ansi_and_prefixes() -> None:
    # ANSI escape sequences + pipes logger prefix + emoji
    raw = "\x1b[31m| status | runner | ❌ ServiceException: Operation failed\x1b[0m"
    cleaned = clean_raw_diagnostic_text(raw)
    assert cleaned == "ServiceException: Operation failed"

    # [Container] prefix + timestamp + [ERROR] + redundant Error:
    raw2 = (
        "[Container] 2026/09/03 16:05:52 2026-09-03 16:05:52.123 "
        "[ERROR] Error: ValidationError: Resource failed"
    )
    cleaned2 = clean_raw_diagnostic_text(raw2)
    assert cleaned2 == "ValidationError: Resource failed"

    # Excessive punctuation
    raw3 = 'Operation in "FAILED" state !!!!. Before continuing...'
    cleaned3 = clean_raw_diagnostic_text(raw3)
    assert cleaned3 == 'Operation in "FAILED" state. Before continuing...'


def test_clean_raw_diagnostic_text_stack_traces() -> None:
    # Multiline Node/TypeScript stack trace
    raw_multiline = (
        "Error: ServiceException: Operation failed\n"
        "    at Function.getLandingZoneOperationStatus (/opt/lza/runner.js:42:10)\n"
        "    at processTicksAndRejections (node:internal/process/task_queues:95:5)"
    )
    cleaned = clean_raw_diagnostic_text(raw_multiline)
    assert cleaned == "ServiceException: Operation failed"
    assert "at Function" not in cleaned
    assert "processTicksAndRejections" not in cleaned

    # Inline single-line concatenated stack trace with trailing .:
    raw_inline = (
        "Error: ServiceException: Operation failed.: "
        "at Function.getLandingZoneOperationStatus (runner.js:42) "
        "at async run (/opt/main.js:10)"
    )
    cleaned_inline = clean_raw_diagnostic_text(raw_inline)
    assert cleaned_inline == "ServiceException: Operation failed."
    assert "at Function" not in cleaned_inline


def test_control_tower_recognizer_and_operation_id_preservation() -> None:
    raw = (
        "| status | runner | ❌ ServiceException: AWS Control Tower Landing Zone operation "
        'with identifier "97258a7b-364e-4321-adcf-f8d860047dac" in "FAILED" state !!!!. '
        "Before continuing, proceed to AWS Control Tower and evaluate the status."
    )
    diag = interpret_failure_diagnostic(raw)

    assert diag.category == FailureCategory.CONTROL_TOWER
    assert diag.operation_id == "97258a7b-364e-4321-adcf-f8d860047dac"
    expected_message = (
        "ServiceException: AWS Control Tower Landing Zone operation "
        "97258a7b-364e-4321-adcf-f8d860047dac is in Failed state. "
        "Before continuing, check the operation in AWS Control Tower."
    )
    assert diag.message == expected_message
    assert diag.raw_text == raw


def test_deduplicate_equivalent_logger_and_raw_exception() -> None:
    line1 = (
        "| status | runner | ❌ ServiceException: AWS Control Tower Landing Zone operation "
        'with identifier "97258a7b-364e-4321-adcf-f8d860047dac" in "FAILED" state !!!!. '
        "Before continuing, proceed to AWS Control Tower and evaluate the status."
    )
    line2 = (
        "Error: ServiceException: AWS Control Tower Landing Zone operation "
        'with identifier "97258a7b-364e-4321-adcf-f8d860047dac" in "FAILED" state !!!!. '
        "Before continuing, proceed to AWS Control Tower and evaluate the status.:\n"
        "    at Function.getLandingZoneOperationStatus (/opt/runner.js:10:5)\n"
        "    at processTicksAndRejections (node:internal/process/task_queues:95:5)"
    )

    stage = MagicMock()
    stage.stage_name = "Prepare"
    action = MagicMock()
    action.action_name = "Prepare"
    action.status = "Failed"
    action.external_execution_id = "build-123"
    action.external_execution_url = "https://console.aws.amazon.com/codebuild/build-123"
    stage.actions = [action]

    failures = collect_pipeline_action_failures(
        [stage],
        fetch_diagnostics=lambda _: [line1, line2],
    )

    assert len(failures) == 1
    fa = failures[0]
    assert fa.stage_name == "Prepare"
    assert fa.action_name == "Prepare"

    # Exactly one concise normalized root cause in diagnostic_details
    assert len(fa.diagnostic_details) == 1
    assert "97258a7b-364e-4321-adcf-f8d860047dac" in fa.diagnostic_details[0]
    assert "❌" not in fa.diagnostic_details[0]
    assert "| status | runner |" not in fa.diagnostic_details[0]
    assert "at Function" not in fa.diagnostic_details[0]

    # Full raw diagnostics retained for debugging / verbose
    assert len(fa.raw_diagnostic_details) == 2
    assert fa.raw_diagnostic_details[0] == line1
    assert fa.raw_diagnostic_details[1] == line2

    # Root cause structured object
    assert fa.root_cause is not None
    assert fa.root_cause.category == FailureCategory.CONTROL_TOWER
    assert fa.root_cause.operation_id == "97258a7b-364e-4321-adcf-f8d860047dac"


def test_distinct_additive_diagnostics_preserved() -> None:
    line1 = (
        "AWSAccelerator-PrepareStack-123 failed: "
        "ValidationError: Stack cannot be deleted while TerminationProtection is enabled"
    )
    line2 = "AWSAccelerator-NetworkStack-456 failed: LimitExceededException: VPC limit reached"

    diag1 = interpret_failure_diagnostic(line1)
    diag2 = interpret_failure_diagnostic(line2)

    deduped = deduplicate_failure_diagnostics([diag1, diag2])
    assert len(deduped) == 2
    assert {d.resource for d in deduped} == {
        "AWSAccelerator-PrepareStack-123",
        "AWSAccelerator-NetworkStack-456",
    }


def test_termination_protection_preservation() -> None:
    raw = (
        "2026-08-23 16:47:44.027 | error | toolkit | Deployment of Stack failed: "
        "❌  AWSAccelerator-PrepareStack-123456789012-eu-west-1 failed: "
        "ValidationError: Stack cannot be deleted while TerminationProtection is enabled"
    )
    err, res = normalize_root_cause_and_resource(raw)
    assert res == "AWSAccelerator-PrepareStack-123456789012-eu-west-1"
    assert err == "ValidationError: Stack cannot be deleted while TerminationProtection is enabled"
    assert "❌" not in err


def test_codebuild_command_and_phase_failures() -> None:
    raw = (
        "[Container] 2026/08/23 Phase context status code: COMMAND_EXECUTION_ERROR "
        "Message: Error while executing command: yarn run ts-node. Reason: exit status 1"
    )
    diag = interpret_failure_diagnostic(raw)
    assert diag.category == FailureCategory.CODEBUILD
    assert "exit status 1" in diag.message or "BUILD phase failed" in diag.message
    assert "yarn run ts-node" not in diag.message


def test_root_cause_selection_prefers_actionable_over_wrapper() -> None:
    diag_wrapper = FailureDiagnostic(
        message="CodeBuild BUILD phase failed (exit status 1)",
        category=FailureCategory.CODEBUILD,
        raw_text="exit status 1",
        specificity=10,
    )
    diag_cfn = FailureDiagnostic(
        message="ValidationError: Stack cannot be deleted while TerminationProtection is enabled",
        category=FailureCategory.CLOUDFORMATION,
        raw_text="...",
        resource="AWSAccelerator-PrepareStack",
        specificity=35,
    )

    root = select_root_cause([diag_wrapper, diag_cfn])
    assert root == diag_cfn
