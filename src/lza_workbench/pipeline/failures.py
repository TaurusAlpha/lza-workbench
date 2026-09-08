"""Pipeline failure interpretation shared by monitoring and status workflows."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from lza_workbench.pipeline.models import PipelineStageState


class FailureCategory(StrEnum):
    """Categorized root causes for pipeline action failures."""

    CONTROL_TOWER = "control_tower"
    CLOUDFORMATION = "cloudformation"
    DEPLOYMENT = "deployment"
    CODEBUILD = "codebuild"
    GENERIC = "generic"


@dataclass(frozen=True)
class FailureDiagnostic:
    """Normalized diagnostic representing an interpreted failure event."""

    message: str
    category: FailureCategory
    raw_text: str
    resource: str | None = None
    operation_id: str | None = None
    specificity: int = 0


@dataclass(frozen=True)
class PipelineActionFailure:
    """Action failure with normalized diagnostics and optional resource attribution."""

    stage_name: str | None
    action_name: str
    summary: str | None
    error_message: str | None
    external_execution_id: str | None
    external_execution_url: str | None
    diagnostic_details: list[str]
    raw_diagnostic_details: list[str]
    failed_resource: str | None
    diagnostics: list[FailureDiagnostic] = field(default_factory=list)
    root_cause: FailureDiagnostic | None = None


def clean_raw_diagnostic_text(raw_text: str) -> str:
    """Perform generic raw-text cleanup stripping ANSI, logger prefixes, and stack traces."""
    line = raw_text.strip()
    if not line:
        return ""

    # Strip ANSI escape sequences
    line = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", line)

    # Strip [Container] timestamp prefix
    line = re.sub(
        r"^\[Container\]\s+\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?\s*",
        "",
        line,
    )

    # Strip ISO timestamps and general timestamps at line start
    line = re.sub(
        r"^\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?\s*",
        "",
        line,
    )

    # Strip pipe-delimited logger prefixes like "| status | runner |" or "| error | toolkit |"
    line = re.sub(r"^(?:\|\s*[\w.-]+\s*)+\|\s*", "", line, flags=re.IGNORECASE)

    # Strip leading deployment wrapper if followed by more content
    while True:
        prev_line = line
        line = re.sub(
            r"^(?:Deployment of (?:Stack )?(?:[\w\-]+ )?failed:\s*)+(?=[^\s])",
            "",
            line,
            flags=re.IGNORECASE,
        ).strip()
        line = re.sub(r"^[❌✖⚠️❗\s]+", "", line).strip()
        if line == prev_line:
            break

    # Strip bracketed log levels like "[ERROR]", "[error]", "[WARN]"
    line = re.sub(
        r"^\[(?:ERROR|error|WARN|warn|INFO|info|DEBUG|debug)\]:?\s*",
        "",
        line,
        flags=re.IGNORECASE,
    )

    # Strip leading presentation emojis like ❌, ✖, ⚠️, ❗
    line = re.sub(r"^[❌✖⚠️❗\s]+", "", line)

    # Strip redundant "Error:" or "ERROR:" prefixes
    line = re.sub(r"^(?:(?:Error|ERROR):\s*)+", "", line)

    # Secondary strip in case prefixes or emojis were chained
    line = re.sub(r"^(?:\|\s*[\w.-]+\s*)+\|\s*", "", line, flags=re.IGNORECASE)
    line = re.sub(r"^[❌✖⚠️❗\s]+", "", line)

    # Strip Node/TypeScript stack frames
    if "\n" in line:
        kept_lines = [
            sub_line
            for sub_line in line.splitlines()
            if not re.match(r"^\s*at\s+(?:async\s+)?[A-Za-z0-9_$.<>[\]]+", sub_line)
        ]
        line = " ".join(sub_line.strip() for sub_line in kept_lines if sub_line.strip())

    # Strip inline stack frames appended on a single line
    line = re.sub(
        r"(?:\n|\s{2,}|\s*:\s*|\s+)at\s+(?:async\s+)?[A-Za-z0-9_$.<>[\]]+(?:\s*\([^)]*\)|[^\n]*).*",
        "",
        line,
        flags=re.DOTALL,
    )

    # Clean excessive exclamation punctuation (e.g. "!!!!.", "!!!!") -> "."
    line = re.sub(r"\s*[!]{2,}\.?", ".", line)

    # Strip trailing punctuation noise like ".:" or trailing ":"
    line = re.sub(r"\.:\s*$", ".", line)
    line = re.sub(r":\s*$", "", line)

    # Clean whitespace before periods
    line = re.sub(r"\s+\.", ".", line)

    # Collapse repeated whitespace
    line = re.sub(r"\s+", " ", line).strip()
    return line


def _recognize_control_tower(cleaned: str, raw_text: str) -> FailureDiagnostic | None:
    """Recognize AWS Control Tower Landing Zone operation failures."""
    match = re.search(
        r"(?:(?P<exc>[A-Za-z0-9_]*Exception|[A-Za-z0-9_]*Error):\s*)?"
        r"AWS Control Tower Landing Zone operation\s+"
        r"(?:with identifier\s+)?[\"']?(?P<op_id>[0-9a-fA-F\-]{36})[\"']?\s+"
        r"(?:in\s+[\"']?(?P<state1>[A-Za-z]+)[\"']?\s+state|is in\s+(?P<state2>[A-Za-z]+)\s+state)"
        r".*?",
        cleaned,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    op_id = match.group("op_id")
    raw_state = match.group("state1") or match.group("state2") or "Failed"
    state = raw_state.capitalize()
    exc_name = match.group("exc") or "ServiceException"

    message = (
        f"{exc_name}: AWS Control Tower Landing Zone operation {op_id} is in {state} state. "
        "Before continuing, check the operation in AWS Control Tower."
    )
    return FailureDiagnostic(
        message=message,
        category=FailureCategory.CONTROL_TOWER,
        raw_text=raw_text,
        resource=None,
        operation_id=op_id,
        specificity=40,
    )


def _recognize_cloudformation(cleaned: str, raw_text: str) -> FailureDiagnostic | None:
    """Recognize CloudFormation stack, validation, termination protection, and resource errors."""
    failed_resource: str | None = None
    msg = cleaned

    # Strip leading deployment wrapper prefixes and emojis to uncover the target resource and error
    while True:
        prev = msg
        msg = re.sub(
            r"^(?:Deployment of (?:Stack )?(?:[\w\-]+ )?failed:\s*)+",
            "",
            msg,
            flags=re.IGNORECASE,
        ).strip()
        msg = re.sub(r"^[❌✖⚠️❗\s]+", "", msg).strip()
        if msg == prev:
            break

    res_match = re.match(
        r"^(?P<resource>[A-Za-z0-9_\-]+(?:Stack|Resource|Project)[A-Za-z0-9_\-]*)\s+failed:\s*(?P<error>.*)$",
        msg,
        flags=re.IGNORECASE,
    )
    if res_match:
        failed_resource = res_match.group("resource")
        err = res_match.group("error").strip()
        err = re.sub(
            r"^(?:Deployment of (?:Stack )?(?:[\w\-]+ )?failed:\s*)+",
            "",
            err,
            flags=re.IGNORECASE,
        ).strip()
        if failed_resource and err.startswith(f"{failed_resource} failed:"):
            err = err[len(failed_resource) + 8 :].strip()
        msg = clean_raw_diagnostic_text(err)

    # Clean generic "DeploymentError: Resource updates failed:" prefix if more details follow
    if re.search(r"^DeploymentError:\s*Resource updates failed:\s*.+", msg, flags=re.IGNORECASE):
        msg = re.sub(
            r"^DeploymentError:\s*Resource updates failed:\s*", "", msg, flags=re.IGNORECASE
        ).strip()

    # Clean leading stack name path prefix from resource
    # (e.g. "StackName/LogicalResourceId" -> "LogicalResourceId")
    if failed_resource:
        msg = re.sub(rf"^{re.escape(failed_resource)}/", "", msg)

    # Clean duplicated custom resource type in parenthesis
    # e.g. "(Custom::Type Type)" -> "(Custom::Type)"
    msg = re.sub(
        r"\(Custom::([A-Za-z0-9_]+)\s+[A-Za-z0-9_]+\)",
        r"(Custom::\1)",
        msg,
    )

    # Check for TerminationProtection
    if "TerminationProtection" in msg or "TerminationProtection" in cleaned:
        if "ValidationError:" in msg:
            val_match = re.search(r"ValidationError:\s*([^\n]+TerminationProtection[^\n]*)", msg)
            if val_match:
                msg = f"ValidationError: {val_match.group(1).strip()}"
        elif not msg.startswith("ValidationError:"):
            msg = f"ValidationError: {msg}"
        return FailureDiagnostic(
            message=msg,
            category=FailureCategory.CLOUDFORMATION,
            raw_text=raw_text,
            resource=failed_resource,
            specificity=35,
        )

    # Check for custom resource failures
    if "Received response status [FAILED]" in msg or "Custom::" in msg:
        msg_ret = re.search(r"Message returned:\s*(.+)$", msg)
        if msg_ret:
            msg = msg_ret.group(1).strip()
        return FailureDiagnostic(
            message=msg,
            category=FailureCategory.CLOUDFORMATION,
            raw_text=raw_text,
            resource=failed_resource,
            specificity=32,
        )

    # Check for ValidationError, StackPolicyException, or other CFN error types
    if any(
        err_type in msg
        for err_type in (
            "ValidationError:",
            "StackPolicyException:",
            "ResourceStatusReason:",
            "StatusReason:",
            "The following resource(s) failed",
        )
    ):
        return FailureDiagnostic(
            message=msg,
            category=FailureCategory.CLOUDFORMATION,
            raw_text=raw_text,
            resource=failed_resource,
            specificity=30,
        )

    if failed_resource:
        return FailureDiagnostic(
            message=msg,
            category=FailureCategory.CLOUDFORMATION,
            raw_text=raw_text,
            resource=failed_resource,
            specificity=25,
        )

    return None


def _recognize_deployment_wrapper(cleaned: str, raw_text: str) -> FailureDiagnostic | None:
    """Recognize LZA/CDK deployment wrapper boilerplate."""
    if re.search(r"^DeploymentError:\s*Resource updates failed:", cleaned, flags=re.IGNORECASE):
        inner = re.sub(
            r"^DeploymentError:\s*Resource updates failed:\s*", "", cleaned, flags=re.IGNORECASE
        ).strip()
        if inner:
            return interpret_failure_diagnostic(inner, original_raw=raw_text)
        return FailureDiagnostic(
            message="DeploymentError: Resource updates failed",
            category=FailureCategory.DEPLOYMENT,
            raw_text=raw_text,
            specificity=15,
        )

    if re.match(
        r"^Deployment of (?:Stack )?(?:[\w\-]+ )?failed:\s*$",
        cleaned,
        flags=re.IGNORECASE,
    ):
        return FailureDiagnostic(
            message=cleaned,
            category=FailureCategory.DEPLOYMENT,
            raw_text=raw_text,
            specificity=15,
        )

    return None


def _recognize_codebuild_failure(cleaned: str, raw_text: str) -> FailureDiagnostic | None:
    """Recognize CodeBuild phase and command execution errors."""
    exit_match = re.search(r"exit (?:status|code)\s+(\d+)", cleaned, flags=re.IGNORECASE)
    if exit_match:
        code = exit_match.group(1)
        phase_match = re.search(r"\b([A-Z_]+)\s+phase\b", cleaned, flags=re.IGNORECASE)
        phase = phase_match.group(1).upper() if phase_match else "BUILD"
        return FailureDiagnostic(
            message=f"CodeBuild {phase} phase failed (exit status {code})",
            category=FailureCategory.CODEBUILD,
            raw_text=raw_text,
            specificity=10,
        )

    if "COMMAND_EXECUTION_ERROR" in cleaned or "Command failed with exit code" in cleaned:
        return FailureDiagnostic(
            message="CodeBuild BUILD phase failed",
            category=FailureCategory.CODEBUILD,
            raw_text=raw_text,
            specificity=10,
        )

    return None


def _recognize_generic(cleaned: str, raw_text: str) -> FailureDiagnostic:
    """Fallback recognizer for generic application or AWS errors."""
    return FailureDiagnostic(
        message=cleaned,
        category=FailureCategory.GENERIC,
        raw_text=raw_text,
        specificity=20,
    )


def interpret_failure_diagnostic(
    raw_text: str,
    *,
    original_raw: str | None = None,
) -> FailureDiagnostic:
    """Parse, clean, and categorize a raw error line into a structured FailureDiagnostic."""
    raw = original_raw or raw_text
    cleaned = clean_raw_diagnostic_text(raw_text)
    if not cleaned:
        return FailureDiagnostic(
            message="",
            category=FailureCategory.GENERIC,
            raw_text=raw,
            specificity=0,
        )

    for recognizer in (
        _recognize_control_tower,
        _recognize_cloudformation,
        _recognize_deployment_wrapper,
        _recognize_codebuild_failure,
    ):
        diag = recognizer(cleaned, raw)
        if diag is not None:
            return diag

    return _recognize_generic(cleaned, raw)


def normalize_root_cause_and_resource(raw_error: str) -> tuple[str, str | None]:
    """Normalize a diagnostic error line by stripping wrapper artifacts and extracting resource."""
    diag = interpret_failure_diagnostic(raw_error)
    return (diag.message, diag.resource)


def _are_diagnostics_equivalent(d1: FailureDiagnostic, d2: FailureDiagnostic) -> bool:
    """Check whether two diagnostics represent the same underlying failure."""
    if d1.message.strip().lower() == d2.message.strip().lower():
        return True

    # Same Control Tower operation
    if (
        d1.category == FailureCategory.CONTROL_TOWER
        and d2.category == FailureCategory.CONTROL_TOWER
        and d1.operation_id
        and d2.operation_id
        and d1.operation_id == d2.operation_id
    ):
        return True

    # Same CloudFormation error on same resource
    if (
        d1.category == FailureCategory.CLOUDFORMATION
        and d2.category == FailureCategory.CLOUDFORMATION
        and d1.resource == d2.resource
    ):
        if "TerminationProtection" in d1.message and "TerminationProtection" in d2.message:
            return True
        if d1.message in d2.message or d2.message in d1.message:
            return True

    # Substring of identical message without wrapper
    if d1.category == d2.category:
        m1, m2 = d1.message.lower(), d2.message.lower()
        if m1 in m2 or m2 in m1:
            return True

    return False


def deduplicate_failure_diagnostics(
    diagnostics: list[FailureDiagnostic],
) -> list[FailureDiagnostic]:
    """Deduplicate equivalent diagnostics while preserving distinct additive failures."""
    unique: list[FailureDiagnostic] = []
    for diag in diagnostics:
        if not diag.message:
            continue

        matched_idx = -1
        for idx, existing in enumerate(unique):
            if _are_diagnostics_equivalent(existing, diag):
                matched_idx = idx
                break

        if matched_idx == -1:
            unique.append(diag)
        else:
            existing = unique[matched_idx]
            # Replace if new diagnostic is more specific or has resource attribution
            if diag.specificity > existing.specificity:
                unique[matched_idx] = diag
            elif (
                diag.specificity == existing.specificity
                and diag.resource
                and not existing.resource
            ):
                unique[matched_idx] = diag
            elif (
                diag.specificity == existing.specificity
                and len(diag.message) > len(existing.message)
            ):
                unique[matched_idx] = diag

    return unique


def select_root_cause(diagnostics: list[FailureDiagnostic]) -> FailureDiagnostic | None:
    """Select the deepest and most actionable failure diagnostic as primary root cause."""
    if not diagnostics:
        return None
    return max(
        diagnostics,
        key=lambda d: (
            d.specificity,
            d.resource is not None,
            len(d.message),
        ),
    )


def collect_pipeline_action_failures(
    stages: Iterable[PipelineStageState],
    *,
    fetch_diagnostics: Callable[[str], list[str]],
) -> list[PipelineActionFailure]:
    """Collect failed actions and derive concise, normalized root-cause diagnostics."""
    failures: list[PipelineActionFailure] = []
    for stage in stages:
        for action in stage.actions:
            if action.status != "Failed":
                continue

            external_execution_id = action.external_execution_id
            diagnostics = fetch_diagnostics(external_execution_id) if external_execution_id else []
            raw_diagnostics = list(diagnostics)
            diagnostic_models: list[FailureDiagnostic] = []

            if diagnostics:
                for diagnostic in diagnostics:
                    diag = interpret_failure_diagnostic(diagnostic)
                    if diag.message:
                        diagnostic_models.append(diag)
            else:
                raw_error = action.error_message or action.summary
                if raw_error:
                    raw_text = str(raw_error)
                    raw_diagnostics = [raw_text]
                    diag = interpret_failure_diagnostic(raw_text)
                    if diag.message:
                        diagnostic_models.append(diag)

            deduped = deduplicate_failure_diagnostics(diagnostic_models)
            root_cause = select_root_cause(deduped)

            failed_resource = root_cause.resource if root_cause and root_cause.resource else None
            if not failed_resource:
                for d in deduped:
                    if d.resource:
                        failed_resource = d.resource
                        break

            diagnostic_details: list[str] = []
            if root_cause:
                diagnostic_details.append(root_cause.message)
                for d in deduped:
                    if d != root_cause and d.message not in diagnostic_details:
                        # Do not include shallow wrappers when a deep root cause is available
                        if root_cause.specificity >= 30 and d.category in {
                            FailureCategory.CODEBUILD,
                            FailureCategory.DEPLOYMENT,
                        }:
                            continue
                        diagnostic_details.append(d.message)
            elif deduped:
                diagnostic_details = [d.message for d in deduped]
            elif raw_diagnostics:
                diagnostic_details = [clean_raw_diagnostic_text(r) or r for r in raw_diagnostics]

            failures.append(
                PipelineActionFailure(
                    stage_name=stage.stage_name,
                    action_name=action.action_name,
                    summary=action.summary,
                    error_message=action.error_message,
                    external_execution_id=external_execution_id,
                    external_execution_url=action.external_execution_url,
                    diagnostic_details=diagnostic_details,
                    raw_diagnostic_details=raw_diagnostics,
                    failed_resource=failed_resource,
                    diagnostics=deduped,
                    root_cause=root_cause,
                )
            )
    return failures


__all__ = [
    "FailureCategory",
    "FailureDiagnostic",
    "PipelineActionFailure",
    "clean_raw_diagnostic_text",
    "collect_pipeline_action_failures",
    "deduplicate_failure_diagnostics",
    "interpret_failure_diagnostic",
    "normalize_root_cause_and_resource",
    "select_root_cause",
]
